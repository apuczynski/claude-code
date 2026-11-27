"""Step 3: new video scripts every day, in the combined style."""

from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path

import yaml

from . import llm, prompts
from .config import DATA_DIR, OUTPUT_DIR, load_brief

log = logging.getLogger(__name__)

REQUIRED = ("niche", "audience")


def check_brief(brief: dict) -> list[str]:
    return [k for k in REQUIRED if not str(brief.get(k) or "").strip()]


def recent_history(scripts_dir: Path, today: dt.date, days: int = 30) -> str:
    """Titles and hooks of the last `days` days of scripts, so topics don't repeat."""
    lines = []
    for f in sorted(scripts_dir.glob("*.md")):
        try:
            d = dt.date.fromisoformat(f.stem)
        except ValueError:
            continue
        if not (today - dt.timedelta(days=days) <= d < today):
            continue
        text = f.read_text()
        for title in re.findall(r"^## Script \d+: (.+)$", text, re.M):
            lines.append(f"- {d}: {title.strip()}")
    return "\n".join(lines) or "(none yet)"


def write_scripts(*, date: dt.date | None = None, n: int | None = None, data_dir: Path = DATA_DIR,
                  out_dir: Path = OUTPUT_DIR / "scripts", brief: dict | None = None, force: bool = False,
                  api=None) -> Path:
    date = date or dt.date.today()
    out = out_dir / f"{date.isoformat()}.md"
    if out.exists() and not force:
        log.info("Scripts for %s already exist: %s", date, out)
        return out
    brief = brief if brief is not None else load_brief()
    missing = check_brief(brief)
    if missing:
        raise SystemExit(f"Fill in {', '.join(missing)} in config/brief.yaml first: the scripts are written for you.")
    guide = data_dir / "style_guide.md"
    if not guide.exists():
        raise SystemExit("No style guide yet. Run collect, analyze, profile and combine first.")

    n = n or int(brief.get("scripts_per_day", 3))
    task = prompts.SCRIPTS_TASK.format(
        date=date.isoformat(),
        n=n,
        brief=yaml.safe_dump(brief, sort_keys=False, allow_unicode=True),
        history=recent_history(out_dir, date),
    )
    # The style guide goes first and stays byte-identical day to day.
    content = [llm.text_block("# STYLE GUIDE\n\n" + guide.read_text()), llm.text_block(task)]
    text = llm.ask(prompts.SCRIPTS_SYSTEM, content, effort="high", api=api)
    out_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# Scripts for {date:%A, %B} {date.day}, {date.year}\n\n{text}\n")
    log.info("Wrote %d scripts to %s", n, out)
    return out
