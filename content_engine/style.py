"""Step 2b and 2c: a style profile for every creator, then one combined style."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import llm, prompts
from .config import DATA_DIR, ROOT, Manifest, load_creator_table
from .page_stats import page_stats
from .selection import views_of

log = logging.getLogger(__name__)


def _post_table(posts: list[dict], limit: int = 400) -> str:
    """Every post on the page as compact CSV-like lines (newest first)."""
    rows = ["shortcode,date,weekday,hour_utc,type,length_s,views,likes,comments,shares,caption_start"]
    for p in sorted(posts, key=lambda p: p["date_utc"], reverse=True)[:limit]:
        cap = (p.get("caption") or "").replace("\n", " ").replace(",", ";")[:90]
        rows.append(",".join(str(x if x is not None else "") for x in (
            p["shortcode"], p["date_utc"][:10], p.get("weekday"), p.get("hour_utc"), p["type"],
            p.get("duration_s") and round(p["duration_s"], 1), views_of(p), p.get("likes"), p.get("comments"),
            p.get("shares"), cap)))
    if len(posts) > limit:
        rows.append(f"... {len(posts) - limit} older posts not listed; they are included in the statistics")
    return "\n".join(rows)


def build_profile_request(username: str, manifest: Manifest, data_dir: Path = DATA_DIR) -> tuple[str, list[dict]]:
    creator = manifest.creators[username]
    videos = manifest.videos_of(username)
    breakdowns = []
    for v in sorted(videos, key=lambda v: ("saved" not in v.picked_by, v.shortcode)):
        f = data_dir / "analysis" / v.shortcode / "breakdown.md"
        if f.exists():
            breakdowns.append(f"<breakdown video='{v.shortcode}' picked_by='{','.join(v.picked_by)}'>\n"
                              f"{f.read_text()}\n</breakdown>")
    if not breakdowns:
        raise RuntimeError(f"No breakdowns for @{username} yet. Run `analyze` first.")

    has_page = bool(creator.page_file and (ROOT / creator.page_file).exists())
    scope = prompts.scope_instructions(creator.scope, creator.deep_sections, creator.extra_focus)
    task = prompts.PROFILE_TASK.format(
        username=username,
        likes="\n".join(f"- {x}" for x in creator.likes),
        scope=scope,
        jk=prompts.JK_WITH_PAGE if has_page else prompts.JK_WITHOUT_PAGE,
    )
    content = [llm.text_block(task), llm.text_block("\n\n".join(breakdowns))]

    if has_page:
        page = json.loads((ROOT / creator.page_file).read_text())
        picked = {v.shortcode for v in videos}
        stats = page_stats(page["posts"], picked)
        comments = {code: cs[:30] for code, cs in page.get("comments", {}).items()}
        content.append(llm.text_block(
            "## PAGE SCAN\n"
            f"Profile:\n```json\n{json.dumps(page['profile'], indent=2, ensure_ascii=False)}\n```\n"
            f"Highlights: {json.dumps(page.get('highlights') or 'not available (needs a logged-in session)')}\n"
            f"Shares: {page.get('shares_note')}\n\n"
            f"Page statistics (computed from every post):\n```json\n{json.dumps(stats, indent=2)}\n```\n\n"
            f"Every post:\n```\n{_post_table(page['posts'])}\n```\n\n"
            f"Comments on the top videos:\n```json\n{json.dumps(comments, indent=1, ensure_ascii=False)}\n```"
        ))
        grid = sorted((data_dir / "creators" / username / "grid").glob("*.jpg"))
        if grid:
            content.append(llm.text_block("Grid covers, newest first, then the profile picture:"))
            for g in grid[:31]:
                content.append(llm.text_block(g.stem))
                content.append(llm.image_block(g))
    return prompts.PROFILE_SYSTEM, content


def build_profile(username: str, manifest: Manifest, *, data_dir: Path = DATA_DIR, force: bool = False,
                  api=None) -> Path:
    out = data_dir / "profiles" / f"{username}.md"
    if out.exists() and not force:
        return out
    system, content = build_profile_request(username, manifest, data_dir)
    text = llm.ask(system, content, effort="high", api=api)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n")
    log.info("@%s: profile written", username)
    return out


def creator_table_text(manifest: Manifest) -> str:
    rows = ["| Reel | Creator | Scan page | Extra focus | Scope | Deepest sections | What the user likes |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    by_reel = {v.reel: v for v in manifest.videos.values() if v.reel is not None}
    for row in load_creator_table().reels:
        v = by_reel.get(row.n)
        who = f"@{v.creator}" if v else "(not collected)"
        rows.append(f"| {row.n} | {who} | {'Yes' if row.scan_page else 'No'} | "
                    f"{'Yes' if row.extra_focus else ''} | {row.scope} | {', '.join(row.deep_sections)} | {row.likes} |")
    return "\n".join(rows)


def build_combined_style(manifest: Manifest, *, data_dir: Path = DATA_DIR, force: bool = False, api=None) -> Path:
    out = data_dir / "style_guide.md"
    if out.exists() and not force:
        return out
    profiles = []
    for username in sorted(manifest.creators):
        f = data_dir / "profiles" / f"{username}.md"
        if f.exists():
            c = manifest.creators[username]
            profiles.append(f"<profile creator='@{username}' reels='{c.reels}' extra_focus='{c.extra_focus}' "
                            f"scope='{c.scope}'>\n{f.read_text()}\n</profile>")
        else:
            log.warning("No profile for @%s; it is left out of the combined style", username)
    if not profiles:
        raise RuntimeError("No creator profiles yet. Run `profile` first.")
    task = prompts.COMBINE_TASK.format(table=creator_table_text(manifest))
    text = llm.ask(prompts.COMBINE_SYSTEM, [llm.text_block(task), llm.text_block("\n\n".join(profiles))],
                   effort="high", api=api)
    out.write_text(text + "\n")
    log.info("Combined style written to %s", out)
    return out
