"""Paths, the creator table, and the user's brief."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

SECTION_NAMES = {
    "A": "Video facts",
    "B": "The hook (first 3 seconds)",
    "C": "Script and structure",
    "D": "On-camera delivery",
    "E": "Editing and cuts",
    "F": "On-screen text and subtitles",
    "G": "Camera, lighting, color and locations",
    "H": "Audio, music and sound effects",
    "I": "Content, topics and post captions",
    "J": "Personal brand (from the whole page)",
    "K": "Performance patterns",
}

# The PRD's "How to use the creator table" mapping: words in the user's note -> sections
# that get the most detail.
_LIKE_KEYWORDS = [
    (("edit",), ["E", "F", "G", "H"]),
    (("page", "brand", "concept", "community"), ["J"]),
    (
        ("educat", "stor", "inspir", "authentic", "engag"),
        ["B", "C", "D", "I"],
    ),
]


def deep_sections_for(likes: str) -> list[str]:
    """Sections to go deepest on, from the user's note about a creator."""
    text = likes.lower()
    out: set[str] = set()
    for words, sections in _LIKE_KEYWORDS:
        if any(w in text for w in words):
            out.update(sections)
    return sorted(out)


_SHORTCODE = re.compile(r"instagram\.com/(?:[^/]+/)?(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)")


def shortcode_from_url(url: str) -> str:
    m = _SHORTCODE.search(url)
    if not m:
        raise ValueError(f"Not an Instagram post or reel link: {url}")
    return m.group(1)


@dataclass
class Reel:
    n: int
    url: str
    scan_page: bool
    extra_focus: bool
    likes: str
    scope: str = "full"  # full | format | message
    deep_sections: list[str] = field(default_factory=list)

    @property
    def shortcode(self) -> str:
        return shortcode_from_url(self.url)


@dataclass
class CreatorTable:
    reels: list[Reel]
    top_by_views: int = 20
    top_by_shares: int = 10


def load_creator_table(path: Path | None = None) -> CreatorTable:
    path = path or CONFIG_DIR / "creators.yaml"
    raw = yaml.safe_load(path.read_text())
    reels = []
    for r in raw["reels"]:
        scope = r.get("scope", "full")
        if scope not in ("full", "format", "message"):
            raise ValueError(f"Reel {r['n']}: scope must be full, format or message, not {scope!r}")
        reel = Reel(
            n=int(r["n"]),
            url=r["url"],
            scan_page=bool(r.get("scan_page", False)),
            extra_focus=bool(r.get("extra_focus", False)),
            likes=r.get("likes", ""),
            scope=scope,
            deep_sections=list(r.get("deep_sections") or deep_sections_for(r.get("likes", ""))),
        )
        reel.shortcode  # validate the link early
        reels.append(reel)
    return CreatorTable(
        reels=reels,
        top_by_views=int(raw.get("top_by_views", 20)),
        top_by_shares=int(raw.get("top_by_shares", 10)),
    )


def load_brief(path: Path | None = None) -> dict:
    path = path or CONFIG_DIR / "brief.yaml"
    return yaml.safe_load(path.read_text()) or {}


# ---------------------------------------------------------------- manifest

@dataclass
class VideoRecord:
    """One video to break down in Step 2."""

    shortcode: str
    creator: str
    url: str
    picked_by: list[str]  # "saved", "top_views", "top_shares"
    post: dict  # the post summary from Step 1 (date, caption, stats ...)
    scope: str = "full"  # full | format | message (from the reel's row; page videos are full)
    reel: int | None = None  # row number in the creator table, for saved reels
    likes: str | None = None  # that row's note, for saved reels
    deep_sections: list[str] = field(default_factory=list)  # that row's deepest sections
    path: str | None = None  # downloaded file, relative to ROOT
    info: dict = field(default_factory=dict)  # extra metadata from the downloader (track, artist ...)
    error: str | None = None


@dataclass
class CreatorRecord:
    username: str
    reels: list[int]  # which rows of the creator table point at this creator
    scan_page: bool
    extra_focus: bool
    scope: str
    likes: list[str]
    deep_sections: list[str]
    page_file: str | None = None  # data/creators/<u>/page.json when the page was scanned


@dataclass
class Manifest:
    creators: dict[str, CreatorRecord]
    videos: dict[str, VideoRecord]

    def save(self, path: Path | None = None) -> Path:
        path = path or DATA_DIR / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "creators": {k: asdict(v) for k, v in sorted(self.creators.items())},
            "videos": {k: asdict(v) for k, v in sorted(self.videos.items())},
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "Manifest":
        path = path or DATA_DIR / "manifest.json"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run `python -m content_engine collect` first.")
        raw = json.loads(path.read_text())
        return cls(
            creators={k: CreatorRecord(**v) for k, v in raw["creators"].items()},
            videos={k: VideoRecord(**v) for k, v in raw["videos"].items()},
        )

    def videos_of(self, username: str) -> list[VideoRecord]:
        return [v for v in self.videos.values() if v.creator == username]


def merge_creator(existing: CreatorRecord | None, reel: Reel, username: str) -> CreatorRecord:
    """Several saved reels can come from one creator: combine their settings."""
    if existing is None:
        return CreatorRecord(
            username=username,
            reels=[reel.n],
            scan_page=reel.scan_page,
            extra_focus=reel.extra_focus,
            scope=reel.scope,
            likes=[reel.likes],
            deep_sections=list(reel.deep_sections),
        )
    existing.reels.append(reel.n)
    existing.scan_page = existing.scan_page or reel.scan_page
    existing.extra_focus = existing.extra_focus or reel.extra_focus
    # The widest scope wins: a full breakdown already covers format and message.
    order = {"message": 0, "format": 1, "full": 2}
    if order[reel.scope] > order[existing.scope]:
        existing.scope = reel.scope
    existing.likes.append(reel.likes)
    existing.deep_sections = sorted(set(existing.deep_sections) | set(reel.deep_sections))
    return existing
