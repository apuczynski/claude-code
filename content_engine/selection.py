"""Step 1: pick which videos on a creator's page to download."""

from __future__ import annotations


def views_of(post: dict) -> int | None:
    """Instagram shows plays on reels and views on older videos; use whichever exists."""
    for key in ("plays", "views"):
        v = post.get(key)
        if v is not None:
            return int(v)
    return None


def select_videos(posts: list[dict], top_by_views: int = 20, top_by_shares: int = 10) -> dict[str, list[str]]:
    """Return {shortcode: ["top_views", "top_shares"]} for the videos to download.

    Only video posts count. Posts with no visible share count are left out of the
    shares ranking (the PRD says to report hidden stats, not guess them).
    """
    videos = [p for p in posts if p.get("type") == "video"]
    picks: dict[str, list[str]] = {}

    by_views = sorted(
        (p for p in videos if views_of(p) is not None),
        key=lambda p: views_of(p),
        reverse=True,
    )[:top_by_views]
    for p in by_views:
        picks.setdefault(p["shortcode"], []).append("top_views")

    by_shares = sorted(
        (p for p in videos if p.get("shares") is not None),
        key=lambda p: p["shares"],
        reverse=True,
    )[:top_by_shares]
    for p in by_shares:
        picks.setdefault(p["shortcode"], []).append("top_shares")

    return picks


def shares_visibility(posts: list[dict]) -> str:
    videos = [p for p in posts if p.get("type") == "video"]
    with_shares = sum(1 for p in videos if p.get("shares") is not None)
    if not videos:
        return "no video posts"
    if with_shares == 0:
        return "share counts are hidden on every video; the top-by-shares list could not be built"
    if with_shares < len(videos):
        return f"share counts visible on {with_shares} of {len(videos)} videos; ranking uses those only"
    return "share counts visible on every video"
