"""Step 1 without instaloader or yt-dlp: import what a person (or a browser agent) collected by hand.

Put everything in data/browser_export/:

  posts.csv       one row per post: every saved reel, and every post on each page marked Scan page = yes
                  creator,shortcode,date,type,views,likes,comments,shares,duration_s,caption
  profiles.csv    optional, one row per scanned creator:
                  creator,full_name,bio,link,followers,highlights
  comments.csv    optional: shortcode,likes,text
  videos/         <shortcode>.mp4 for each video to break down (from SnapInsta or any downloader)
  covers/<creator>/  optional screenshots of the profile grid, for Section J

Run `python -m content_engine import-browser` once posts.csv is filled in: it writes the list of
videos to download (to_download.txt). Download those into videos/, then run it again.
"""

from __future__ import annotations

import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR

EXPORT_DIR = DATA_DIR / "browser_export"
POST_COLUMNS = ["creator", "shortcode", "date", "type", "views", "likes", "comments", "shares",
                "duration_s", "caption"]


def _num(v: str | None):
    """'12.3K', '1,204', '1.1M', '' -> int or None (blank = not visible)."""
    if v is None:
        return None
    s = str(v).strip().replace(",", "").lower()
    if not s or s in ("-", "n/a", "hidden", "none"):
        return None
    mult = 1
    if s.endswith("k"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000, s[:-1]
    return int(round(float(s) * mult))


def _date(v: str) -> datetime:
    s = v.strip().replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


class BrowserExportSource:
    """Serves Step 1 from data/browser_export/ instead of from Instagram."""

    logged_in = True  # comments/highlights come from the files, if present

    def __init__(self, export_dir: Path = EXPORT_DIR):
        self.dir = export_dir
        rows = _read(export_dir / "posts.csv")
        if not rows:
            raise SystemExit(f"{export_dir / 'posts.csv'} is missing or empty.")
        missing = [c for c in ("creator", "shortcode", "type") if c not in rows[0]]
        if missing:
            raise SystemExit(f"posts.csv needs the columns {', '.join(POST_COLUMNS)} (missing: {', '.join(missing)})")
        self.posts_by_code: dict[str, dict] = {}
        for r in rows:
            p = self._summary(r)
            self.posts_by_code[p["shortcode"]] = p
        self.profiles = {r["creator"].lstrip("@"): r for r in _read(export_dir / "profiles.csv")}
        self.comment_rows: dict[str, list[dict]] = {}
        for r in _read(export_dir / "comments.csv"):
            self.comment_rows.setdefault(r["shortcode"], []).append({"text": r.get("text"), "likes": _num(r.get("likes"))})
        self.pages_opened: list[str] = []

    def _summary(self, r: dict) -> dict:
        code = r["shortcode"]
        if "instagram.com" in code:
            from .config import shortcode_from_url

            code = shortcode_from_url(code)
        kind = r["type"].lower()
        kind = {"reel": "video", "clip": "video", "sidecar": "carousel", "image": "photo"}.get(kind, kind)
        d = _date(r["date"]) if r.get("date") else None
        dur = r.get("duration_s")
        caption = r.get("caption", "")
        return {
            "shortcode": code,
            "url": f"https://www.instagram.com/p/{code}/",
            "owner": r["creator"].lstrip("@"),
            "date_utc": d.isoformat() if d else "",
            "weekday": d.strftime("%A") if d else None,
            "hour_utc": d.hour if d and ("T" in r["date"] or " " in r["date"].strip()) else None,
            "type": kind,
            "caption": caption,
            "hashtags": [w[1:] for w in caption.split() if w.startswith("#")],
            "mentions": [w[1:] for w in caption.split() if w.startswith("@")],
            "tagged_users": [],
            "plays": _num(r.get("views")) if kind == "video" else None,
            "views": None,
            "likes": _num(r.get("likes")),
            "comments": _num(r.get("comments")),
            "shares": _num(r.get("shares")),
            "saves": None,
            "duration_s": float(dur) if dur else None,
            "is_pinned": False,
            "cover_url": None,
            "video_url": None,
        }

    # -- InstagramSource
    def post(self, shortcode: str) -> dict:
        if shortcode not in self.posts_by_code:
            raise SystemExit(f"Saved reel {shortcode} isn't in posts.csv. Add a row for it (its creator, date, stats).")
        return dict(self.posts_by_code[shortcode])

    def profile(self, username: str) -> dict:
        self.pages_opened.append(username)
        r = self.profiles.get(username, {})
        return {"username": username, "full_name": r.get("full_name"), "biography": r.get("bio"),
                "external_url": r.get("link"), "followers": _num(r.get("followers")),
                "profile_pic_url": None, "note": None if r else "no row in profiles.csv"}

    def posts(self, username: str):
        return [dict(p) for p in self.posts_by_code.values() if p["owner"] == username]

    def comments(self, shortcode: str, limit: int) -> list[dict]:
        return self.comment_rows.get(shortcode, [])[:limit]

    def highlights(self, username: str) -> list[dict]:
        h = self.profiles.get(username, {}).get("highlights", "")
        return [{"title": t.strip()} for t in h.split(";") if t.strip()]

    def download_file(self, url: str, dest: Path) -> Path:
        raise FileNotFoundError("covers come from covers/<creator>/")

    def download_video(self, post: dict, dest_dir: Path) -> tuple[Path, dict]:
        src = self.dir / "videos" / f"{post['shortcode']}.mp4"
        if not src.exists():
            raise FileNotFoundError(f"{src.name} not in {self.dir / 'videos'} yet")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if not dest.exists():
            shutil.copy2(src, dest)
        return dest, {}


def import_export(table, export_dir: Path = EXPORT_DIR, data_dir: Path = DATA_DIR):
    """Build the manifest from the export. Returns (manifest, shortcodes still to download)."""
    from .collect import collect

    src = BrowserExportSource(export_dir)
    manifest = collect(table, src, data_dir=data_dir, grid_covers=0)
    for username in manifest.creators:
        covers = export_dir / "covers" / username
        if covers.is_dir():
            grid = data_dir / "creators" / username / "grid"
            grid.mkdir(parents=True, exist_ok=True)
            for f in sorted(covers.iterdir()):
                if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    shutil.copy2(f, grid / f.name)
    todo = sorted(v.shortcode for v in manifest.videos.values()
                  if not v.path and (v.error or "").startswith("download failed"))
    lines = [f"https://www.instagram.com/p/{c}/" for c in todo]
    (export_dir / "to_download.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
    return manifest, todo
