import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory) -> Path:
    """A 5 s vertical 1080x1920 video with hard cuts at 1.5 s and 3.2 s, a steady tone, and
    two loud clicks at 2.0 s and 4.0 s standing in for sound effects."""
    out = tmp_path_factory.mktemp("media") / "sample.mp4"
    v = ("color=c=red:s=1080x1920:d=1.5:r=30[a];color=c=blue:s=1080x1920:d=1.7:r=30[b];"
         "color=c=green:s=1080x1920:d=1.8:r=30[c];[a][b][c]concat=n=3:v=1:a=0[v]")
    a = ("sine=f=220:d=5:sample_rate=44100,volume=0.05[tone];"
         "sine=f=1000:d=0.1:sample_rate=44100,volume=0.9,adelay=2000|2000,apad=whole_dur=5[c1];"
         "sine=f=1200:d=0.1:sample_rate=44100,volume=0.9,adelay=4000|4000,apad=whole_dur=5[c2];"
         "[tone][c1][c2]amix=inputs=3:normalize=0[aout]")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-filter_complex", f"{v};{a}", "-map", "[v]", "-map", "[aout]",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", "5", str(out)],
        check=True,
    )
    return out


FAKE_WORDS = [
    {"start": 0.4, "end": 0.7, "word": "Stop", "p": 0.99},
    {"start": 0.7, "end": 1.0, "word": "scrolling.", "p": 0.99},
    {"start": 1.6, "end": 1.9, "word": "This", "p": 0.99},
    {"start": 1.9, "end": 2.1, "word": "changed", "p": 0.99},
    {"start": 2.1, "end": 2.4, "word": "everything.", "p": 0.99},
    {"start": 3.3, "end": 3.6, "word": "Follow", "p": 0.99},
    {"start": 3.6, "end": 3.9, "word": "for", "p": 0.99},
    {"start": 3.9, "end": 4.3, "word": "more.", "p": 0.99},
]


@pytest.fixture
def fake_transcribe(monkeypatch):
    from content_engine import media

    def _t(path, model_size="small", language=None):
        return {"language": "en", "model": "fake",
                "segments": [{"start": 0.4, "end": 4.3, "text": "Stop scrolling. This changed everything. Follow for more."}],
                "words": FAKE_WORDS}

    monkeypatch.setattr(media, "transcribe", _t)


class FakeClaude:
    """Stands in for anthropic.Anthropic(): records requests, returns canned text."""

    def __init__(self, reply="# breakdown\n\n## A. Video facts\n- ok", stop_reason="end_turn"):
        self.calls = []
        self.reply = reply
        self.stop_reason = stop_reason
        outer = self

        class _Stream:
            def __init__(self, kw):
                self.kw = kw

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get_final_message(self):
                return SimpleNamespace(
                    stop_reason=outer.stop_reason,
                    stop_details=SimpleNamespace(category="test", explanation="declined"),
                    content=[SimpleNamespace(type="thinking", thinking=""),
                             SimpleNamespace(type="text", text=outer.reply)],
                    usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0),
                )

        class _Messages:
            def stream(self, **kw):
                outer.calls.append(kw)
                return _Stream(kw)

        self.beta = SimpleNamespace(messages=_Messages())


@pytest.fixture
def fake_claude():
    return FakeClaude()
