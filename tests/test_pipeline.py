import datetime as dt
import json
from pathlib import Path

import pytest

from content_engine import analyze, collect as collect_mod, llm, media, metrics, scripts, style
from content_engine.config import (CreatorTable, Reel, deep_sections_for, load_creator_table,
                                   shortcode_from_url)
from content_engine.page_stats import page_stats
from content_engine.selection import select_videos, shares_visibility
from tests.conftest import FakeClaude

# ------------------------------------------------------------------ config


def test_creator_table_matches_prd():
    t = load_creator_table()
    assert [r.n for r in t.reels] == list(range(1, 13))
    assert t.top_by_views == 20 and t.top_by_shares == 10
    by_n = {r.n: r for r in t.reels}
    assert {n for n, r in by_n.items() if r.extra_focus} == {1, 4, 6, 7, 9}
    assert {n for n, r in by_n.items() if not r.scan_page} == {5, 11, 12}
    assert by_n[5].scope == "format" and by_n[11].scope == "message" and by_n[12].scope == "message"
    assert by_n[3].shortcode == "DeGnaliAvQW"  # a /p/ link


def test_deep_sections_follow_prd_mapping():
    # "branding, page, concept, education" -> J + B, C, D, I
    assert deep_sections_for("really good branding, a really good page, a great concept, and great education") == [
        "B", "C", "D", "I", "J"]
    assert deep_sections_for("Very engaging. Great editing.") == ["B", "C", "D", "E", "F", "G", "H", "I"]
    assert deep_sections_for("Loves the authenticity. Inspirational.") == ["B", "C", "D", "I"]


def test_shortcode_parsing():
    assert shortcode_from_url("https://www.instagram.com/reel/DgLPuk1yc_9/") == "DgLPuk1yc_9"
    assert shortcode_from_url("https://www.instagram.com/someone/reel/Abc-123/?igsh=x") == "Abc-123"
    with pytest.raises(ValueError):
        shortcode_from_url("https://example.com/video")


# ------------------------------------------------------------------ selection


def _posts(n=40):
    out = []
    for i in range(n):
        out.append({"shortcode": f"v{i:02d}", "type": "video" if i % 4 else "photo", "plays": i * 1000,
                    "shares": (n - i) * 10 if i % 2 else None, "date_utc": f"2026-0{1 + i % 9}-1{i % 9}T12:00:00+00:00",
                    "weekday": "Monday", "hour_utc": 12, "likes": i * 50, "comments": i, "duration_s": 10 + i,
                    "caption": "Comment GUIDE and follow for more #tips", "hashtags": ["tips"]})
    return out


def test_select_top_by_views_and_shares():
    posts = _posts()
    picks = select_videos(posts, 20, 10)
    videos = [p for p in posts if p["type"] == "video"]
    top_views = sorted(videos, key=lambda p: p["plays"], reverse=True)[:20]
    assert all("top_views" in picks[p["shortcode"]] for p in top_views)
    assert sum("top_shares" in w for w in picks.values()) == 10
    assert not any(p["type"] == "photo" for p in posts if p["shortcode"] in picks)
    assert "ranking uses those only" in shares_visibility(posts)


def test_hidden_shares_are_reported_not_guessed():
    posts = [{**p, "shares": None} for p in _posts()]
    picks = select_videos(posts, 20, 10)
    assert not any("top_shares" in w for w in picks.values())
    assert "hidden" in shares_visibility(posts)


def test_page_stats():
    posts = _posts()
    s = page_stats(posts, {"v39", "v38"})
    assert s["posts_total"] == 40
    assert s["top_videos_picked"]["posts"] == 2
    assert s["calls_to_action_in_captions"]["follow"] == "40 of 40 posts"
    assert s["by_length"]


# ------------------------------------------------------------------ measurements


def test_measurements_on_a_real_video(sample_video, tmp_path, fake_transcribe):
    m = analyze.measure(sample_video, tmp_path)
    f = m["file"]
    assert f["aspect_ratio"] == "9:16" and f["width"] == 1080 and f["height"] == 1920
    assert abs(f["duration_s"] - 5) < 0.1 and round(f["fps"]) == 30
    starts = [s["start"] for s in m["shots"]]
    assert len(starts) == 3 and abs(starts[1] - 1.5) < 0.05 and abs(starts[2] - 3.2) < 0.05
    e = m["editing"]
    assert e["cuts"] == 2 and e["longest_shot"]["shot"] == 3
    sp = m["speech"]
    assert sp["time_to_first_word_s"] == 0.4 and sp["spoken_words"] == 8 and sp["sentences"] == 3
    assert sp["closing_line"] == "Follow for more."
    jumps = m["audio"]["loudness_jumps"]
    assert any(abs(t - 2.0) < 0.05 for t in jumps) and any(abs(t - 4.0) < 0.05 for t in jumps)
    assert (tmp_path / "measurements.json").exists()

    frames = analyze.frames_for(sample_video, m, tmp_path)
    times = [t for t, _ in frames]
    assert {0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0} <= set(times)  # the hook, every 0.5 s
    assert 0.75 in times  # the middle of shot 1
    assert 3.2 + 0.05 in [round(t, 2) for t in times]  # the start of shot 3
    assert all(p.exists() for _, p in frames)


def test_frame_plan_is_capped():
    shots = metrics.shots_from_cuts([i * 0.3 for i in range(1, 200)], 60.0)
    plan = metrics.plan_frames(shots, 60.0, max_frames=90)
    assert len(plan) <= 90 and {0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0} <= set(plan)
    assert all(b - a >= 0.149 for a, b in zip(plan, plan[1:]))


def test_transcribe_failure_is_not_fatal(sample_video, monkeypatch):
    def boom(size):
        raise OSError("model download blocked")

    monkeypatch.setattr(media, "_whisper", boom)
    assert media.transcribe(sample_video) is None


# ------------------------------------------------------------------ collect


class FakeSource:
    def __init__(self, video_file: Path):
        self.video_file = video_file
        self.pages_opened = []
        self.logged_in = True

    def _post(self, code, owner, plays=1000, shares=None):
        return {"shortcode": code, "url": f"https://www.instagram.com/p/{code}/", "owner": owner,
                "date_utc": "2026-10-01T15:00:00+00:00", "weekday": "Thursday", "hour_utc": 15, "type": "video",
                "caption": "hi #x", "hashtags": ["x"], "mentions": [], "tagged_users": [], "plays": plays,
                "views": None, "likes": 10, "comments": 2, "shares": shares, "saves": None, "duration_s": 5.0,
                "is_pinned": False, "cover_url": None, "video_url": None}

    def post(self, code):
        return self._post(code, "scanme" if code == "SAVED1" else "dontscan")

    def profile(self, u):
        self.pages_opened.append(u)
        return {"username": u, "biography": "bio", "profile_pic_url": None}

    def posts(self, u):
        self.pages_opened.append(u)
        return [self._post(f"P{i}", u, plays=i * 100, shares=i) for i in range(30)] + [self._post("SAVED1", u, 99999)]

    def comments(self, code, limit):
        return [{"text": "love this", "likes": 3}]

    def highlights(self, u):
        return [{"title": "Start here", "cover_url": None}]

    def download_file(self, url, dest):
        raise AssertionError("no covers in this fake")

    def download_video(self, post, dest_dir):
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / f"{post['shortcode']}.mp4"
        out.write_bytes(self.video_file.read_bytes())
        return out, {"track": "Original audio"}


def test_collect_scans_only_pages_marked_yes(sample_video, tmp_path):
    table = CreatorTable(reels=[
        Reel(1, "https://www.instagram.com/reel/SAVED1/", True, True, "great editing", "full", ["E", "F", "G", "H"]),
        Reel(2, "https://www.instagram.com/reel/SAVED2/", False, False, "the message", "message", []),
    ], top_by_views=5, top_by_shares=3)
    src = FakeSource(sample_video)
    m = collect_mod.collect(table, src, data_dir=tmp_path / "data")
    assert set(src.pages_opened) == {"scanme"}  # never opened the page marked "No"
    assert m.creators["scanme"].page_file and not m.creators["dontscan"].page_file
    assert m.videos["SAVED2"].scope == "message" and m.videos["SAVED2"].picked_by == ["saved"]
    # SAVED1 is also the page's most-viewed video: one record, both reasons.
    assert m.videos["SAVED1"].picked_by[0] == "saved" and "top_views" in m.videos["SAVED1"].picked_by
    scanme = m.videos_of("scanme")
    assert sum("top_views" in v.picked_by for v in scanme) == 5
    assert sum("top_shares" in v.picked_by for v in scanme) == 3
    assert all(v.path for v in m.videos.values())
    page = json.loads((tmp_path / "data/creators/scanme/page.json").read_text())
    assert len(page["posts"]) == 31 and page["comments"]


# ------------------------------------------------------------------ Claude steps (fake API)


def test_full_pipeline_with_fake_claude(sample_video, tmp_path, fake_transcribe, monkeypatch):
    data = tmp_path / "data"
    table = CreatorTable(reels=[
        Reel(1, "https://www.instagram.com/reel/SAVED1/", True, True, "great editing", "full", ["E", "F", "G", "H"]),
        Reel(2, "https://www.instagram.com/reel/SAVED2/", False, False, "the message", "message", []),
    ], top_by_views=2, top_by_shares=1)
    m = collect_mod.collect(table, FakeSource(sample_video), data_dir=data)
    monkeypatch.setattr(style, "load_creator_table", lambda: table)

    api = FakeClaude()
    done = analyze.analyze_all(m, workers=2, data_dir=data, api=api)
    assert len(done) == len(m.videos)
    req = next(c for c in api.calls if "SAVED1" in c["messages"][0]["content"][0]["text"])
    assert req["model"] == llm.MODEL == "claude-opus-5-5"
    assert req["fallbacks"] == "default" and req["betas"] == [llm.FALLBACK_BETA]
    assert req["output_config"] == {"effort": "high"}
    blocks = req["messages"][0]["content"]
    assert sum(b["type"] == "image" for b in blocks) >= 9
    intro = blocks[0]["text"]
    assert "EXTRA FOCUS" in intro and "Sections E, F, G, H" in intro and '"cuts": 2' in intro
    assert "Stop@0.40" in intro
    assert "Shot-by-shot log" in blocks[-1]["text"]
    msg_req = next(c for c in api.calls if "SAVED2" in c["messages"][0]["content"][0]["text"])
    assert "only the message and the story" in msg_req["messages"][0]["content"][0]["text"]
    assert "Shot-by-shot log" not in msg_req["messages"][0]["content"][-1]["text"]

    # Profiles: the scanned creator gets J and K with page stats; the other says there's no page.
    api.calls.clear()
    style.build_profile("scanme", m, data_dir=data, api=api)
    style.build_profile("dontscan", m, data_dir=data, api=api)
    scan_text = "\n".join(b.get("text", "") for b in api.calls[0]["messages"][0]["content"])
    assert "K. Performance patterns" in scan_text and "posts_per_week_all_time" in scan_text
    assert "love this" in scan_text
    assert "Skip Sections J and K" in api.calls[1]["messages"][0]["content"][0]["text"]

    api.calls.clear()
    guide = style.build_combined_style(m, data_dir=data, api=api)
    assert guide.exists()
    combine_text = api.calls[0]["messages"][0]["content"][0]["text"]
    assert "Reels 11 and 12 contribute only their message and story" in combine_text
    assert "| 1 | @scanme | Yes | Yes |" in combine_text

    # Step 3
    out_dir = tmp_path / "scripts"
    (out_dir).mkdir()
    (out_dir / "2026-11-26.md").write_text("## Script 1: Yesterday's topic\n")
    api.reply = "## Script 1: New topic\n..."
    brief = {"niche": "fitness for nurses", "audience": "night-shift nurses", "scripts_per_day": 2}
    p = scripts.write_scripts(date=dt.date(2026, 11, 27), data_dir=data, out_dir=out_dir, brief=brief, api=api)
    assert p.name == "2026-11-27.md" and "Friday, November 27, 2026" in p.read_text()
    task = api.calls[-1]["messages"][0]["content"][1]["text"]
    assert "Write 2 new video scripts" in task and "Yesterday's topic" in task
    assert api.calls[-1]["messages"][0]["content"][0]["text"].startswith("# STYLE GUIDE")


def test_scripts_need_a_brief(tmp_path):
    (tmp_path / "style_guide.md").write_text("x")
    with pytest.raises(SystemExit, match="niche, audience"):
        scripts.write_scripts(data_dir=tmp_path, out_dir=tmp_path / "s", brief={"niche": ""}, api=FakeClaude())


def test_refusal_raises():
    with pytest.raises(llm.ClaudeError, match="declined"):
        llm.ask("sys", [llm.text_block("hi")], api=FakeClaude(stop_reason="refusal"))


def test_truncation_is_marked():
    out = llm.ask("sys", [llm.text_block("hi")], api=FakeClaude(reply="long", stop_reason="max_tokens"))
    assert out.startswith("long") and "length limit" in out


def test_summarize_instaloader_post():
    from datetime import datetime
    from types import SimpleNamespace

    p = SimpleNamespace(
        typename="GraphVideo", is_video=True, shortcode="ABC", owner_username="maker",
        date_utc=datetime(2026, 11, 2, 18, 30), caption="Big news #a #b", caption_hashtags=["a", "b"],
        caption_mentions=[], tagged_users=["friend"], video_play_count=12000, video_view_count=9000,
        likes=-1, comments=40, video_duration=31.5, is_pinned=True, url="https://cdn/x.jpg",
        video_url="https://cdn/x.mp4", _node={"share_count": 77},
    )
    s = collect_mod.summarize_post(p)
    assert s["type"] == "video" and s["weekday"] == "Monday" and s["hour_utc"] == 18
    assert s["plays"] == 12000 and s["likes"] is None and s["shares"] == 77 and s["saves"] is None
    carousel = SimpleNamespace(**{**vars(p), "typename": "GraphSidecar", "is_video": False, "_node": {}})
    s2 = collect_mod.summarize_post(carousel)
    assert s2["type"] == "carousel" and s2["plays"] is None and s2["shares"] is None


def test_browser_export_two_passes(sample_video, tmp_path):
    from content_engine.browser_import import _num, import_export

    assert _num("12.3K") == 12300 and _num("1,204") == 1204 and _num("1.1M") == 1_100_000 and _num("") is None
    export = tmp_path / "export"
    (export / "videos").mkdir(parents=True)
    rows = ["creator,shortcode,date,type,views,likes,comments,shares,duration_s,caption",
            "@scanme,SAVED1,2026-11-02T18:30:00Z,reel,2.5M,40K,900,3.1K,34,\"Big one #tips\"",
            "dontscan,SAVED2,2026-10-01,video,10K,500,20,,20,message"]
    rows += [f"scanme,P{i},2026-09-{i + 1:02d}T12:00:00Z,video,{i}K,{i * 10},{i},{i},15,post {i}" for i in range(25)]
    rows += ["scanme,PHOTO,2026-08-01,photo,,300,4,,,a photo"]
    (export / "posts.csv").write_text("\n".join(rows) + "\n")
    (export / "profiles.csv").write_text("creator,full_name,bio,link,followers,highlights\nscanme,Scan Me,bio,,12K,Start;FAQ\n")
    (export / "comments.csv").write_text("shortcode,likes,text\nSAVED1,5,so good\n")
    (export / "covers" / "scanme").mkdir(parents=True)
    (export / "covers" / "scanme" / "grid_1.png").write_bytes(b"png")

    table = CreatorTable(reels=[
        Reel(1, "https://www.instagram.com/reel/SAVED1/", True, True, "great editing", "full", ["E"]),
        Reel(2, "https://www.instagram.com/reel/SAVED2/", False, False, "the message", "message", []),
    ], top_by_views=5, top_by_shares=3)
    data = tmp_path / "data"

    # Pass 1: nothing downloaded yet -> the list of what to get.
    m, todo = import_export(table, export, data)
    assert "SAVED1" in todo and "SAVED2" in todo and "PHOTO" not in todo
    assert len(todo) == len(m.videos)
    assert (export / "to_download.txt").read_text().count("instagram.com") == len(todo)
    page = json.loads((data / "creators/scanme/page.json").read_text())
    assert page["profile"]["followers"] == 12000 and page["highlights"][1]["title"] == "FAQ"
    assert page["comments"]["SAVED1"][0]["text"] == "so good"
    assert m.videos["SAVED1"].post["plays"] == 2_500_000 and m.videos["SAVED1"].post["hour_utc"] == 18
    assert not (data / "creators/dontscan/page.json").exists()

    # Pass 2: the videos are in -> everything ready.
    for code in todo:
        (export / "videos" / f"{code}.mp4").write_bytes(sample_video.read_bytes())
    m, todo = import_export(table, export, data)
    assert todo == [] and all(v.path for v in m.videos.values())
    assert (data / "creators/scanme/grid/grid_1.png").exists()
