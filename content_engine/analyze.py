"""Step 2a: break down every downloaded video (Sections A to I + the shot log)."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import llm, media, metrics, prompts
from .config import DATA_DIR, ROOT, Manifest, VideoRecord

log = logging.getLogger(__name__)


def fmt_t(t: float) -> str:
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:04.1f}"


def measure(video_path: Path, out_dir: Path, *, whisper_model: str = "small", force: bool = False) -> dict:
    """Run every measurement once and cache it in measurements.json."""
    out = out_dir / "measurements.json"
    if out.exists() and not force:
        return json.loads(out.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)

    facts = media.probe(video_path)
    duration = facts["duration_s"]
    cuts = media.detect_cuts(video_path)
    shots = metrics.shots_from_cuts(cuts, duration)
    transcript = media.transcribe(video_path, whisper_model) if facts["has_audio"] else None
    words = transcript["words"] if transcript else []
    samples = media.load_audio(video_path) if facts["has_audio"] else None
    hop = 0.02
    env = media.loudness_envelope(samples) if samples is not None else None
    transients = media.detect_transients(env, hop) if env is not None else []
    silences = media.detect_silences(video_path) if facts["has_audio"] else []

    result = {
        "file": facts,
        "shots": [{"shot": s.index, "start": s.start, "end": s.end, "length_s": s.length} for s in shots],
        "editing": metrics.editing_metrics(shots, duration),
        "speech": metrics.speech_metrics(words, duration, shots),
        "audio": (metrics.audio_metrics(env, hop, words, transients, cuts, silences, duration)
                  if env is not None else {"note": "no audio track"}),
        "transcript": transcript or {"note": "no transcript (no audio, or faster-whisper not installed)"},
    }
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def frames_for(video_path: Path, m: dict, out_dir: Path, max_frames: int = 90) -> list[tuple[float, Path]]:
    shots = [metrics.Shot(s["shot"], s["start"], s["end"]) for s in m["shots"]]
    times = metrics.plan_frames(shots, m["file"]["duration_s"], max_frames=max_frames)
    out = []
    for t in times:
        p = out_dir / "frames" / f"t{t:07.2f}.jpg"
        if p.exists() or media.extract_frame(video_path, t, p):
            out.append((t, p))
    return out


def _post_facts(rec: VideoRecord) -> dict:
    p = rec.post
    views = p.get("plays") or p.get("views")
    per_k = {}
    if views:
        for k in ("likes", "comments", "shares"):
            if p.get(k) is not None:
                per_k[f"{k}_per_1000_views"] = round(p[k] / views * 1000, 2)
    hidden = [k for k in ("plays", "views", "likes", "comments", "shares", "saves") if p.get(k) is None]
    return {
        "link": rec.url,
        "creator": "@" + rec.creator,
        "posted_utc": p.get("date_utc"),
        "weekday": p.get("weekday"),
        "picked_by": rec.picked_by,
        "plays": p.get("plays"),
        "views": p.get("views"),
        "likes": p.get("likes"),
        "comments": p.get("comments"),
        "shares": p.get("shares"),
        **per_k,
        "not_visible": hidden,
        "caption": p.get("caption"),
        "hashtags": p.get("hashtags"),
        "mentions": p.get("mentions"),
        "tagged_users": p.get("tagged_users"),
        "audio_track": {k: rec.info[k] for k in ("track", "artist") if k in rec.info} or "not shown",
    }


def build_request(rec: VideoRecord, m: dict, frames: list[tuple[float, Path]], creator_likes: list[str],
                  deep: list[str], extra_focus: bool) -> tuple[str, list[dict]]:
    sections = prompts.VIDEO_SECTIONS
    if rec.scope == "message":
        sections = ["A", "B", "C", "I"]
    wanted = "\n\n".join(prompts.SECTIONS[s] for s in sections)

    # Word-timed transcript in a compact form: one line per segment, then the word timings.
    transcript = m.get("transcript", {})
    lines = [f"[{fmt_t(s['start'])}-{fmt_t(s['end'])}] {s['text']}" for s in transcript.get("segments", [])]
    words = " ".join(f"{w['word']}@{w['start']:.2f}" for w in transcript.get("words", []))
    measurements = {k: v for k, v in m.items() if k != "transcript"}

    intro = f"""\
# Video {rec.shortcode} by @{rec.creator}

What the user likes about this creator: {" / ".join(creator_likes)}

{prompts.scope_instructions(rec.scope, deep, extra_focus)}

## POST FACTS
```json
{json.dumps(_post_facts(rec), indent=2, ensure_ascii=False)}
```

## MEASUREMENTS (ffmpeg + speech model; use as given)
```json
{json.dumps(measurements, indent=2, ensure_ascii=False)}
```

## TRANSCRIPT
{chr(10).join(lines) or "(none)"}

Word timings (word@seconds):
{words or "(none)"}

## FRAMES
{len(frames)} frames follow, each preceded by its timestamp. Hook frames are every 0.5 s for the
first 3 s; after that, the start and middle of each measured shot.
"""
    content: list[dict] = [llm.text_block(intro)]
    for t, p in frames:
        content.append(llm.text_block(f"Frame at {fmt_t(t)}"))
        content.append(llm.image_block(p))
    content.append(llm.text_block(
        "Now write the breakdown. Start with `# {code} by @{u}`, then these sections:\n\n{s}".format(
            code=rec.shortcode, u=rec.creator, s=wanted)
    ))
    return prompts.BREAKDOWN_SYSTEM, content


def analyze_video(rec: VideoRecord, manifest: Manifest, *, data_dir: Path = DATA_DIR,
                  whisper_model: str = "small", force: bool = False, remeasure: bool | None = None,
                  api=None) -> Path | None:
    if not rec.path:
        log.warning("%s: skipped (%s)", rec.shortcode, rec.error or "not downloaded")
        return None
    out_dir = data_dir / "analysis" / rec.shortcode
    out = out_dir / "breakdown.md"
    if out.exists() and not force:
        return out
    video = ROOT / rec.path
    m = measure(video, out_dir, whisper_model=whisper_model, force=force if remeasure is None else remeasure)
    frames = frames_for(video, m, out_dir)
    creator = manifest.creators[rec.creator]
    # A saved reel uses its own row's note; videos found on the page use the creator's.
    likes = [rec.likes] if rec.likes else creator.likes
    deep = rec.deep_sections or creator.deep_sections
    system, content = build_request(rec, m, frames, likes, deep, creator.extra_focus)
    text = llm.ask(system, content, effort="high", api=api)
    out.write_text(text + "\n")
    log.info("%s: breakdown written", rec.shortcode)
    return out


def analyze_all(manifest: Manifest, *, only: list[str] | None = None, limit: int | None = None,
                workers: int = 3, **kw) -> list[Path]:
    todo = [v for v in manifest.videos.values() if v.path and (not only or v.creator in only)]
    # Saved reels first, then the rest by creator.
    todo.sort(key=lambda v: ("saved" not in v.picked_by, v.creator, v.shortcode))
    if limit:
        todo = todo[:limit]
    log.info("Breaking down %d videos with %s", len(todo), llm.MODEL)
    # Measuring is CPU-bound and loads the speech model; do it one at a time first.
    for v in todo:
        try:
            measure(ROOT / v.path, kw.get("data_dir", DATA_DIR) / "analysis" / v.shortcode,
                    whisper_model=kw.get("whisper_model", "small"), force=kw.get("force", False))
        except Exception as e:
            log.error("%s: measuring failed: %s", v.shortcode, e)
    done = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(analyze_video, v, manifest, remeasure=False, **kw): v for v in todo}
        for f in as_completed(futures):
            v = futures[f]
            try:
                p = f.result()
                if p:
                    done.append(p)
            except Exception as e:
                log.error("%s: breakdown failed: %s", v.shortcode, e)
    return done
