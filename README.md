# Daily Content Engine

Learns the styles of the Instagram creators you like, then writes you new video scripts every day,
with instructions for how to record and edit each one. It follows the *Daily Content Engine — PRD*.

| PRD step | Command | What it does | Output |
| --- | --- | --- | --- |
| Input | edit `config/creators.yaml` | The 12 saved reels, Scan page, Extra focus, and what you like about each | — |
| 1. Collect | `collect` | Reads each saved reel. For creators marked Scan page = yes, records every post on their page (date, type, caption, views, likes, comments, shares), then downloads their top 20 videos by views and top 10 by shares. Never opens the pages marked No. | `data/manifest.json`, `data/creators/<name>/` |
| 2. Learn styles | `analyze` | Measures every video (cuts, shot lengths, word timings, pauses, loudness), pulls frames, and has Claude write the Section A–I breakdown with a shot-by-shot log | `data/analysis/<video>/breakdown.md` |
| | `profile` | One style profile per creator: every category in numbers, 3 examples per finding, Sections J and K from the page scan, and a "how to copy it" section | `data/profiles/<name>.md` |
| | `combine` | One combined style, weighted the way the PRD says (Extra focus most; reels 11–12 message only; the reel 5 green-screen format included) | `data/style_guide.md` |
| 3. Daily scripts | `scripts` | Today's scripts in that style, each with hook, timed script, how to record it, how to edit it, and the caption | `output/scripts/YYYY-MM-DD.md` |

## How the breakdown works

Claude can look at images but can't watch video or hear audio, so each video is split into the
part a program can measure and the part Claude judges from frames:

- **Measured** (ffmpeg, [faster-whisper](https://github.com/SYSTRAN/faster-whisper)): length, resolution, frame rate, aspect ratio; every cut and so every shot's start, end and length; cuts per second overall and per third; a transcript with a timestamp on every word; words per minute; time to first word and first cut; pauses; sentence lengths; words between cuts; loudness while talking versus between words; sudden loudness jumps (candidate sound effects or beat hits) and whether cuts land on them.
- **Judged by Claude** (Opus 5.5, from those numbers plus up to 90 frames per video: every 0.5 s through the hook, then the start and middle of each shot): framing, on-screen text and subtitle style, b-roll, overlays, zooms, lighting, locations, hook type, beat map, storytelling devices, delivery, topic and purpose.

Following the PRD's rules, every finding cites a video and timestamp. Anything that can't be seen or measured is reported as such, not guessed. Three cases come up often:

- **Saves** are never visible to other accounts.
- **Share counts** are often hidden. When they are, the top-by-shares list can't be built and the report says so. If you can see share counts in the app, put them in `config/shares.csv` (`shortcode,shares`, one per line) and they're used.
- **Sound effects** are named only as unconfirmed candidates, matched to a loudness jump and what's on screen at that moment.

## Setup (on your computer)

Instagram blocks cloud servers, so Steps 1 and 2 run on your own computer.

1. Install [Python 3.11+](https://www.python.org/downloads/) and [ffmpeg](https://ffmpeg.org/download.html) (`brew install ffmpeg` on a Mac).
2. In this folder:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Get a Claude API key from [console.anthropic.com](https://console.anthropic.com/) and set it:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```
4. Log in to Instagram once, so the page scan can read comments, highlights and the reels tab:
   ```bash
   instaloader --login YOUR_INSTAGRAM_USERNAME
   ```
5. Fill in `config/brief.yaml` (your niche, audience, equipment). The scripts are written for you,
   so Step 3 won't run without it.

## Run it

Try it on a few videos first to check quality and cost:

```bash
python -m content_engine collect --login YOUR_INSTAGRAM_USERNAME --cookies-from-browser chrome
python -m content_engine status
python -m content_engine analyze --limit 3
```

Then the rest:

```bash
python -m content_engine analyze     # skips videos already done
python -m content_engine profile
python -m content_engine combine
python -m content_engine scripts     # today's scripts
```

### Step 1 another way: collect in a browser (SnapInsta)

If you'd rather not use instaloader and yt-dlp, collect Step 1 by hand or with a browser agent,
and the program takes it from there:

1. In `data/browser_export/`, fill in `posts.csv` (templates in `config/browser_export_templates/`):
   one row for each saved reel, and one for every post on each page marked Scan page = yes. Copy
   numbers as Instagram shows them (`12.3K` is fine), and leave hidden ones blank. Optionally add
   `profiles.csv`, `comments.csv`, and grid screenshots in `covers/<creator>/`.
2. `python -m content_engine import-browser` writes `data/browser_export/to_download.txt`: the
   saved reels plus each scanned creator's top 20 by views and top 10 by shares.
3. Download those (for example with SnapInsta) into `data/browser_export/videos/` as `<shortcode>.mp4`.
4. Run `import-browser` again. Once it says every video is in, continue with `analyze`.

`python -m content_engine all --login YOUR_INSTAGRAM_USERNAME` runs collect through combine in one go.
Every step skips work that's already done; add `--force` to redo it. `--creator NAME` limits
`analyze` and `profile` to one creator.

The first `analyze` downloads the speech model (about 500 MB for `small`). `--whisper tiny` is
faster and less accurate; `--whisper large-v3` is the most accurate.

## Every day

Pick one:

- **GitHub Actions** (no computer needed): commit `data/style_guide.md` (the only file under `data/`
  that git tracks), add an `ANTHROPIC_API_KEY` secret under the repository's Settings → Secrets and
  variables → Actions, and `.github/workflows/daily-scripts.yml` writes and commits
  `output/scripts/<date>.md` every day at 11:17 UTC. Change the `cron` line for another time.
- **cron on your computer**: `crontab -e`, then
  `0 7 * * * cd /path/to/this/folder && .venv/bin/python -m content_engine scripts`
  (with `ANTHROPIC_API_KEY` set in that line or your shell profile).

Each day's run reads the last 30 days of scripts so topics and hooks don't repeat.

## Cost

These are rough estimates at Claude Opus 5.5 prices ($4 / $20 per million input / output tokens).
`analyze --limit 3` shows the real token counts in the log.

| Step | Per item | Whole run (about 9 page scans × up to 30 videos + 3 saved reels) |
| --- | --- | --- |
| Video breakdown | ~$0.40–0.50 per video (about 70k input tokens, mostly frames, plus 6–10k output) | ~$80–140 |
| Creator profile | ~$1–2 per creator | ~$15 |
| Combined style | ~$1 | ~$1 |
| Daily scripts | ~$0.25 per day | ~$8 a month |

Steps 1–2 run once (or when you add creators). Only Step 3 runs every day.

## Notes

- If Claude declines a request, the API retries it on a fallback model automatically
  (`fallbacks: "default"`). A request that's still declined is logged and skipped.
- Instaloader pauses between requests to go easy on Instagram. Scanning a big page takes a while,
  and Instagram may still rate-limit your account. If it does, wait and rerun `collect`; videos already
  downloaded are kept.
- Set `CONTENT_ENGINE_MODEL` to use a different Claude model.
- Tests: `python -m pytest` (uses a generated video and a fake Claude; no network needed).
