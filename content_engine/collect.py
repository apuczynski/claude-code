"""Step 1: collect each creator's videos.

- Every saved reel in the creator table is downloaded.
- Scan page = yes: every post on the creator's page is recorded (date, type, caption,
  views, likes, comments, shares), then the top 20 videos by views and the top 10 by
  shares are downloaded.
- Scan page = no: the creator's page is never opened. Only the saved reel is used.

Instagram data comes from instaloader (logged in with your own session) and videos are
downloaded with yt-dlp. Both sit behind `InstagramSource`, so tests can swap in a fake.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
import urllib.request
from datetime import timezone
from pathlib import Path
from typing import Iterable, Protocol

from .config import (
    DATA_DIR,
    ROOT,
    CreatorTable,
    Manifest,
    VideoRecord,
    merge_creator,
)
from .selection import select_videos, shares_visibility

log = logging.getLogger(__name__)


class InstagramSource(Protocol):
    def post(self, shortcode: str) -> dict: ...
    def profile(self, username: str) -> dict: ...
    def posts(self, username: str) -> Iterable[dict]: ...
    def comments(self, shortcode: str, limit: int) -> list[dict]: ...
    def highlights(self, username: str) -> list[dict]: ...
    def download_file(self, url: str, dest: Path) -> Path: ...
    def download_video(self, post: dict, dest_dir: Path) -> tuple[Path, dict]: ...


# ------------------------------------------------------------------ instaloader + yt-dlp


def _non_negative(v):
    if v is None:
        return None
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None  # instaloader returns -1 for hidden counts


def _share_count(post) -> int | None:
    """Instagram sometimes includes a share count in the raw post data. Use it if so."""
    node = getattr(post, "_node", None) or {}
    for key in ("share_count", "reshare_count", "media_repost_count"):
        if key in node:
            return _non_negative(node[key])
    return None


def summarize_post(post) -> dict:
    """An instaloader Post -> the plain dict the rest of the pipeline uses."""
    typename = post.typename or ""
    if post.is_video:
        kind = "video"
    elif "Sidecar" in typename:
        kind = "carousel"
    else:
        kind = "photo"
    date = post.date_utc.replace(tzinfo=timezone.utc)
    return {
        "shortcode": post.shortcode,
        "url": f"https://www.instagram.com/p/{post.shortcode}/",
        "owner": post.owner_username,
        "date_utc": date.isoformat(),
        "weekday": date.strftime("%A"),
        "hour_utc": date.hour,
        "type": kind,
        "caption": post.caption or "",
        "hashtags": list(post.caption_hashtags or []),
        "mentions": list(post.caption_mentions or []),
        "tagged_users": list(getattr(post, "tagged_users", []) or []),
        "plays": _non_negative(getattr(post, "video_play_count", None)) if post.is_video else None,
        "views": _non_negative(getattr(post, "video_view_count", None)) if post.is_video else None,
        "likes": _non_negative(post.likes),
        "comments": _non_negative(post.comments),
        "shares": _share_count(post),
        "saves": None,  # Instagram never shows saves to other accounts
        "duration_s": getattr(post, "video_duration", None),
        "is_pinned": bool(getattr(post, "is_pinned", False)),
        "cover_url": post.url,
        "video_url": post.video_url if post.is_video else None,
    }


class InstaloaderSource:
    """Real Instagram access. Log in once with `instaloader --login YOUR_USERNAME`."""

    def __init__(self, session_user: str | None = None, cookies_from_browser: str | None = None,
                 cookies_file: str | None = None, pause_s: float = 2.0):
        import instaloader

        self._il = instaloader
        self.loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            save_metadata=False,
            quiet=True,
        )
        self.logged_in = False
        if session_user:
            self.loader.load_session_from_file(session_user)
            self.logged_in = True
        self.cookies_from_browser = cookies_from_browser
        self.cookies_file = cookies_file
        self.pause_s = pause_s

    def _pause(self):
        time.sleep(self.pause_s)  # go easy on Instagram

    def post(self, shortcode: str) -> dict:
        p = self._il.Post.from_shortcode(self.loader.context, shortcode)
        return summarize_post(p)

    def profile(self, username: str) -> dict:
        p = self._il.Profile.from_username(self.loader.context, username)
        return {
            "username": p.username,
            "full_name": p.full_name,
            "biography": p.biography,
            "external_url": p.external_url,
            "followers": p.followers,
            "following": p.followees,
            "post_count": p.mediacount,
            "is_verified": p.is_verified,
            "category": p.business_category_name,
            "profile_pic_url": p.profile_pic_url,
        }

    def posts(self, username: str) -> Iterable[dict]:
        p = self._il.Profile.from_username(self.loader.context, username)
        seen: set[str] = set()
        for post in p.get_posts():
            seen.add(post.shortcode)
            yield summarize_post(post)
        # Reels that don't appear in the main grid.
        if self.logged_in:
            try:
                for post in p.get_reels():
                    if post.shortcode not in seen:
                        seen.add(post.shortcode)
                        yield summarize_post(post)
            except Exception as e:  # the reels tab needs a login and isn't always available
                log.warning("Could not read the reels tab of %s: %s", username, e)

    def comments(self, shortcode: str, limit: int) -> list[dict]:
        if not self.logged_in:
            return []
        p = self._il.Post.from_shortcode(self.loader.context, shortcode)
        out = []
        for c in p.get_comments():
            out.append({
                "text": c.text,
                "likes": getattr(c, "likes_count", None),
                "date_utc": c.created_at_utc.isoformat() if c.created_at_utc else None,
                "by_creator": c.owner.username == p.owner_username,
                "replies_from_creator": sum(
                    1 for a in getattr(c, "answers", []) or [] if a.owner.username == p.owner_username
                ),
            })
            if len(out) >= limit:
                break
        self._pause()
        return out

    def highlights(self, username: str) -> list[dict]:
        if not self.logged_in:
            return []
        p = self._il.Profile.from_username(self.loader.context, username)
        return [{"title": h.title, "cover_url": h.cover_url} for h in self.loader.get_highlights(p)]

    def download_file(self, url: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        return dest

    def download_video(self, post: dict, dest_dir: Path) -> tuple[Path, dict]:
        """yt-dlp first (it also returns the music track); the post's direct video link as a fallback."""
        import yt_dlp

        dest_dir.mkdir(parents=True, exist_ok=True)
        opts = {
            "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }
        if self.cookies_from_browser:
            opts["cookiesfrombrowser"] = (self.cookies_from_browser,)
        if self.cookies_file:
            opts["cookiefile"] = self.cookies_file
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(post["url"], download=True)
                if info.get("_type") == "playlist":  # a carousel: keep the first video
                    info = next(e for e in info["entries"] if e)
                path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
                if not path.exists():
                    path = Path(ydl.prepare_filename(info))
            keep = ("title", "description", "track", "artist", "album", "duration", "width", "height",
                    "fps", "like_count", "comment_count", "view_count", "repost_count", "channel",
                    "uploader", "timestamp")
            return path, {k: info.get(k) for k in keep if info.get(k) is not None}
        except Exception as e:
            if not post.get("video_url"):
                raise
            log.warning("yt-dlp failed for %s (%s); using the direct video link", post["shortcode"], e)
            path = self.download_file(post["video_url"], dest_dir / f"{post['shortcode']}.mp4")
            return path, {}


# ------------------------------------------------------------------ the step


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def _load_share_overrides(path: Path) -> dict[str, int]:
    """Optional shares.csv (shortcode,shares) for counts you read off the app yourself."""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith("shortcode"):
            continue
        code, _, n = line.partition(",")
        if n.strip():
            out[code.strip()] = int(n.strip().replace(",", ""))
    return out


def collect(
    table: CreatorTable,
    source: InstagramSource,
    *,
    data_dir: Path = DATA_DIR,
    comments_per_video: int = 50,
    grid_covers: int = 30,
    download: bool = True,
) -> Manifest:
    data_dir.mkdir(parents=True, exist_ok=True)
    share_overrides = _load_share_overrides(data_dir.parent / "config" / "shares.csv")
    manifest = Manifest(creators={}, videos={})

    # 1. The saved reels: read each one (this does not open the creator's page).
    for reel in table.reels:
        log.info("Reel %d: reading %s", reel.n, reel.url)
        post = source.post(reel.shortcode)
        if reel.shortcode in share_overrides:
            post["shares"] = share_overrides[reel.shortcode]
        username = post["owner"]
        manifest.creators[username] = merge_creator(manifest.creators.get(username), reel, username)
        manifest.videos[reel.shortcode] = VideoRecord(
            shortcode=reel.shortcode,
            creator=username,
            url=reel.url,
            picked_by=["saved"],
            post=post,
            scope=reel.scope,
            reel=reel.n,
            likes=reel.likes,
            deep_sections=list(reel.deep_sections),
        )

    # 2. Scan page = yes: record every post on the page, then pick the top videos.
    for username, creator in manifest.creators.items():
        if not creator.scan_page:
            continue
        log.info("Scanning the whole page of @%s", username)
        cdir = data_dir / "creators" / username
        cdir.mkdir(parents=True, exist_ok=True)
        profile = source.profile(username)
        posts = list(source.posts(username))
        for p in posts:
            if p["shortcode"] in share_overrides:
                p["shares"] = share_overrides[p["shortcode"]]
        highlights = source.highlights(username)
        picks = select_videos(posts, table.top_by_views, table.top_by_shares)
        page = {
            "profile": profile,
            "highlights": highlights,
            "posts": posts,
            "shares_note": shares_visibility(posts),
            "logged_in": getattr(source, "logged_in", None),
        }

        # Grid covers (newest first) and the profile picture, for Section J.
        if download:
            for i, p in enumerate(sorted(posts, key=lambda p: p["date_utc"], reverse=True)[:grid_covers]):
                if p.get("cover_url"):
                    try:
                        source.download_file(p["cover_url"], cdir / "grid" / f"{i:02d}_{p['shortcode']}.jpg")
                    except Exception as e:
                        log.warning("Cover %s: %s", p["shortcode"], e)
            if profile.get("profile_pic_url"):
                try:
                    source.download_file(profile["profile_pic_url"], cdir / "grid" / "profile_pic.jpg")
                except Exception as e:
                    log.warning("Profile picture of %s: %s", username, e)

        by_code = {p["shortcode"]: p for p in posts}
        for code, why in picks.items():
            rec = manifest.videos.get(code)
            if rec:
                for w in why:
                    if w not in rec.picked_by:
                        rec.picked_by.append(w)
                rec.post = {**by_code[code], **{k: v for k, v in rec.post.items() if v is not None}}
            else:
                manifest.videos[code] = VideoRecord(
                    shortcode=code,
                    creator=username,
                    url=by_code[code]["url"],
                    picked_by=list(why),
                    post=by_code[code],
                )

        # Comments on the top videos, for Section K.
        page["comments"] = {}
        for code in picks:
            try:
                page["comments"][code] = source.comments(code, comments_per_video)
            except Exception as e:
                log.warning("Comments on %s: %s", code, e)
        (cdir / "page.json").write_text(json.dumps(page, indent=2, ensure_ascii=False))
        creator.page_file = _rel(cdir / "page.json")
        log.info("@%s: %d posts, %d videos picked (%s)", username, len(posts), len(picks), page["shares_note"])

    # 3. Download every picked video.
    for rec in manifest.videos.values():
        kind = rec.post.get("type")
        # A saved carousel may hold a video (yt-dlp keeps the first one); photos have none.
        if kind != "video" and not (kind == "carousel" and "saved" in rec.picked_by):
            rec.error = f"not a video post (type: {kind}); nothing to download"
            continue
        if not download:
            continue
        vdir = data_dir / "creators" / rec.creator / "videos"
        existing = vdir / f"{rec.shortcode}.mp4"
        if existing.exists():
            rec.path = _rel(existing)
            continue
        try:
            path, info = source.download_video(rec.post, vdir)
            rec.path, rec.info = _rel(path), info
        except Exception as e:
            rec.error = f"download failed: {e}"
            log.error("Download %s failed: %s", rec.shortcode, e)

    manifest.save(data_dir / "manifest.json")
    return manifest
