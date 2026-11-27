"""Numbers for Sections J and K, computed from the full page scan."""

from __future__ import annotations

import re
import statistics
from collections import Counter
from datetime import datetime

from .selection import views_of

LENGTH_BUCKETS = [(0, 15), (15, 30), (30, 60), (60, 90), (90, 10_000)]
CTA_PATTERNS = {
    "comment a keyword / comment": r"\bcomment\b",
    "link in bio": r"link in (my )?bio",
    "follow": r"\bfollow\b",
    "DM": r"\b(dm|message me)\b",
    "save": r"\bsave\b",
    "share / send": r"\b(share|send this)\b",
}


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def _rate(p, key):
    v = views_of(p)
    if not v or p.get(key) is None:
        return None
    return p[key] / v * 1000


def page_stats(posts: list[dict], picked: set[str]) -> dict:
    if not posts:
        return {"note": "no posts found"}
    dates = sorted(datetime.fromisoformat(p["date_utc"]) for p in posts)
    span_days = max((dates[-1] - dates[0]).days, 1)
    gaps = [(b - a).total_seconds() / 86400 for a, b in zip(dates, dates[1:])]
    recent = [d for d in dates if (dates[-1] - d).days <= 90]
    types = Counter(p["type"] for p in posts)
    videos = [p for p in posts if p["type"] == "video"]

    def group_stats(group):
        return {
            "posts": len(group),
            "median_views": _median([views_of(p) for p in group]),
            "median_likes_per_1000_views": _median([_rate(p, "likes") for p in group]),
            "median_comments_per_1000_views": _median([_rate(p, "comments") for p in group]),
            "median_shares_per_1000_views": _median([_rate(p, "shares") for p in group]),
        }

    by_length = {}
    for lo, hi in LENGTH_BUCKETS:
        g = [p for p in videos if p.get("duration_s") is not None and lo <= p["duration_s"] < hi]
        if g:
            by_length[f"{lo}-{hi if hi < 10_000 else '+'}s"] = group_stats(g)
    by_weekday = {d: group_stats(g) for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                                              "Saturday", "Sunday")
                  if (g := [p for p in videos if p.get("weekday") == d])}
    by_hour = {}
    for lo in range(0, 24, 4):
        g = [p for p in videos if p.get("hour_utc") is not None and lo <= p["hour_utc"] < lo + 4]
        if g:
            by_hour[f"{lo:02d}-{lo + 4:02d} UTC"] = group_stats(g)

    top = [p for p in videos if p["shortcode"] in picked]
    rest = [p for p in videos if p["shortcode"] not in picked]
    captions = [p.get("caption") or "" for p in posts]
    cta = {name: sum(1 for c in captions if re.search(rx, c, re.I)) for name, rx in CTA_PATTERNS.items()}
    oldest = sorted(posts, key=lambda p: p["date_utc"])[:10]
    newest = sorted(posts, key=lambda p: p["date_utc"], reverse=True)[:10]

    def brief(p):
        first = (p.get("caption") or "").strip().splitlines()[0][:120] if p.get("caption") else ""
        return {"shortcode": p["shortcode"], "date": p["date_utc"][:10], "type": p["type"],
                "length_s": p.get("duration_s"), "views": views_of(p), "caption_first_line": first}

    return {
        "posts_total": len(posts),
        "first_post": dates[0].date().isoformat(),
        "latest_post": dates[-1].date().isoformat(),
        "posts_per_week_all_time": round(len(posts) / span_days * 7, 2),
        "posts_per_week_last_90_days": round(len(recent) / 90 * 7, 2),
        "days_between_posts": {"median": _median(gaps), "longest": round(max(gaps), 1) if gaps else None,
                               "std_dev": round(statistics.pstdev(gaps), 1) if len(gaps) > 1 else None},
        "type_mix": {k: f"{v} ({v / len(posts):.0%})" for k, v in types.items()},
        "pinned_posts": [p["shortcode"] for p in posts if p.get("is_pinned")],
        "video_length_s": {"median": _median([p.get("duration_s") for p in videos]),
                           "min": min((p["duration_s"] for p in videos if p.get("duration_s")), default=None),
                           "max": max((p["duration_s"] for p in videos if p.get("duration_s")), default=None)},
        "all_videos": group_stats(videos),
        "top_videos_picked": group_stats(top),
        "rest_of_videos": group_stats(rest),
        "top_vs_rest_median_length_s": {"top": _median([p.get("duration_s") for p in top]),
                                        "rest": _median([p.get("duration_s") for p in rest])},
        "by_length": by_length,
        "by_weekday": by_weekday,
        "by_posting_hour": by_hour,
        "hashtags_per_post_median": _median([len(p.get("hashtags") or []) for p in posts]),
        "caption_length_chars_median": _median([len(c) for c in captions]),
        "calls_to_action_in_captions": {k: f"{v} of {len(posts)} posts" for k, v in cta.items()},
        "oldest_posts": [brief(p) for p in oldest],
        "newest_posts": [brief(p) for p in newest],
    }
