"""Command line: python -m content_engine <step> [options]

  collect   Step 1: read the saved reels, scan pages, download videos
  analyze   Step 2: measure and break down every video (Sections A-I)
  profile   Step 2: a style profile for every creator (+ J and K)
  combine   Step 2: one combined style guide
  scripts   Step 3: today's scripts
  all       collect, analyze, profile and combine in one go
  status    what's been done so far
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

from .config import DATA_DIR, Manifest, load_creator_table


def _collect(a):
    from .collect import InstaloaderSource, collect

    src = InstaloaderSource(session_user=a.login, cookies_from_browser=a.cookies_from_browser,
                            cookies_file=a.cookies)
    if not a.login:
        logging.warning("No --login given: comments, highlights and the reels tab need a logged-in "
                        "session, and Instagram may block anonymous page scans.")
    m = collect(load_creator_table(), src, comments_per_video=a.comments)
    ok = sum(1 for v in m.videos.values() if v.path)
    print(f"Collected {len(m.creators)} creators and {ok} of {len(m.videos)} videos. "
          f"See {DATA_DIR / 'manifest.json'}")


def _analyze(a):
    from .analyze import analyze_all

    m = Manifest.load()
    done = analyze_all(m, only=a.creator, limit=a.limit, workers=a.workers, whisper_model=a.whisper,
                       force=a.force)
    print(f"{len(done)} breakdowns in {DATA_DIR / 'analysis'}")


def _profile(a):
    from .style import build_profile

    m = Manifest.load()
    for u in a.creator or sorted(m.creators):
        try:
            print(build_profile(u, m, force=a.force))
        except Exception as e:
            logging.error("@%s: %s", u, e)


def _combine(a):
    from .style import build_combined_style

    print(build_combined_style(Manifest.load(), force=a.force))


def _scripts(a):
    from .scripts import write_scripts

    date = dt.date.fromisoformat(a.date) if a.date else None
    print(write_scripts(date=date, n=a.n, force=a.force))


def _all(a):
    _collect(a)
    a.creator, a.limit = None, None
    _analyze(a)
    _profile(a)
    _combine(a)


def _status(a):
    try:
        m = Manifest.load()
    except FileNotFoundError as e:
        print(e)
        return
    print(f"{'creator':<28}{'reels':<10}{'scan':<6}{'focus':<7}{'videos':>7}{'downloaded':>12}{'broken down':>13}  profile")
    for u, c in sorted(m.creators.items()):
        vs = m.videos_of(u)
        dl = sum(1 for v in vs if v.path)
        bd = sum(1 for v in vs if (DATA_DIR / "analysis" / v.shortcode / "breakdown.md").exists())
        prof = "yes" if (DATA_DIR / "profiles" / f"{u}.md").exists() else "-"
        print(f"@{u:<27}{','.join(map(str, c.reels)):<10}{'yes' if c.scan_page else 'no':<6}"
              f"{'yes' if c.extra_focus else '':<7}{len(vs):>7}{dl:>12}{bd:>13}  {prof}")
    errors = [v for v in m.videos.values() if v.error]
    for v in errors:
        print(f"  ! {v.shortcode} (@{v.creator}): {v.error}")
    print("style guide:", "yes" if (DATA_DIR / "style_guide.md").exists() else "not yet")


def main(argv=None):
    p = argparse.ArgumentParser(prog="content_engine", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def collect_opts(sp):
        sp.add_argument("--login", help="Instagram username whose instaloader session to use "
                                        "(create it once with: instaloader --login USERNAME)")
        sp.add_argument("--cookies-from-browser", help="browser yt-dlp reads Instagram cookies from, e.g. chrome")
        sp.add_argument("--cookies", help="cookies.txt file for yt-dlp")
        sp.add_argument("--comments", type=int, default=50, help="comments to read per top video")

    def analyze_opts(sp):
        sp.add_argument("--creator", action="append", help="only this creator (repeatable)")
        sp.add_argument("--limit", type=int, help="break down at most this many videos")
        sp.add_argument("--workers", type=int, default=3, help="Claude requests in parallel")
        sp.add_argument("--whisper", default="small", help="faster-whisper model size (tiny ... large-v3)")

    sp = sub.add_parser("collect", help="Step 1")
    collect_opts(sp)
    sp.set_defaults(fn=_collect)

    sp = sub.add_parser("analyze", help="Step 2: video breakdowns")
    analyze_opts(sp)
    sp.add_argument("--force", action="store_true", help="redo work that's already done")
    sp.set_defaults(fn=_analyze)

    sp = sub.add_parser("profile", help="Step 2: creator profiles")
    sp.add_argument("--creator", action="append")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=_profile)

    sp = sub.add_parser("combine", help="Step 2: combined style guide")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=_combine)

    sp = sub.add_parser("scripts", help="Step 3: today's scripts")
    sp.add_argument("--n", type=int, help="how many (default: scripts_per_day in brief.yaml)")
    sp.add_argument("--date", help="YYYY-MM-DD (default: today)")
    sp.add_argument("--force", action="store_true", help="rewrite if that day's file exists")
    sp.set_defaults(fn=_scripts)

    sp = sub.add_parser("all", help="Steps 1 and 2 end to end")
    collect_opts(sp)
    analyze_opts(sp)
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=_all)

    sp = sub.add_parser("status", help="progress so far")
    sp.set_defaults(fn=_status)

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
