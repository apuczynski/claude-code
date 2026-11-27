"""Step 2, the measurable part: what ffmpeg and a speech model can count or time.

Everything here is a measurement, never a guess. Claude reads these numbers alongside
the frames; it does not re-estimate them.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def probe(path: Path) -> dict:
    """Length, size, frame rate and aspect ratio."""
    r = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {r.stderr.strip()}")
    meta = json.loads(r.stdout)
    video = next((s for s in meta["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in meta["streams"] if s["codec_type"] == "audio"), None)
    if video is None:
        raise RuntimeError(f"{path} has no video stream")
    w, h = int(video["width"]), int(video["height"])
    rot = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = abs(int(sd["rotation"]))
    if rot in (90, 270):
        w, h = h, w
    fps = float(Fraction(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")) if (
        video.get("avg_frame_rate", "0/0") != "0/0") else None
    ratio = Fraction(w, h).limit_denominator(32)
    return {
        "duration_s": round(float(meta["format"]["duration"]), 3),
        "width": w,
        "height": h,
        "aspect_ratio": f"{ratio.numerator}:{ratio.denominator}",
        "fps": round(fps, 3) if fps else None,
        "has_audio": audio is not None,
        "video_codec": video.get("codec_name"),
        "bitrate_kbps": round(int(meta["format"].get("bit_rate", 0)) / 1000) or None,
    }


_PTS = re.compile(r"pts_time:([0-9.]+)")


def detect_cuts(path: Path, threshold: float = 0.3) -> list[float]:
    """Timestamps (s) where the picture changes sharply: hard cuts, jump cuts, most transitions.

    Smooth zooms and slow dissolves can slip under the threshold; the frames sent to
    Claude around each shot cover those.
    """
    r = _run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-vf", f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-",
    ])
    times = [float(m.group(1)) for m in _PTS.finditer(r.stderr)]
    # Merge detections closer than 3 frames (a flash or a fast transition counts once).
    out: list[float] = []
    for t in sorted(times):
        if not out or t - out[-1] > 0.1:
            out.append(round(t, 3))
    return out


def detect_silences(path: Path, noise_db: float = -35.0, min_s: float = 0.25) -> list[tuple[float, float]]:
    r = _run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_s}", "-vn", "-f", "null", "-",
    ])
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", r.stderr)]
    out = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        out.append((round(s, 3), round(e, 3) if e is not None else None))
    return out


def load_audio(path: Path, sr: int = SAMPLE_RATE) -> np.ndarray:
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-vn", "-ac", "1",
         "-ar", str(sr), "-f", "s16le", "-"],
        capture_output=True, check=False,
    )
    if r.returncode != 0 or not r.stdout:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def loudness_envelope(samples: np.ndarray, sr: int = SAMPLE_RATE, hop_s: float = 0.02) -> np.ndarray:
    """RMS level in dBFS per 20 ms window."""
    hop = int(sr * hop_s)
    if len(samples) < hop:
        return np.zeros(0)
    n = len(samples) // hop
    frames = samples[: n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms)


def detect_transients(env_db: np.ndarray, hop_s: float = 0.02, jump_db: float = 12.0,
                      floor_db: float = -45.0) -> list[float]:
    """Sudden jumps in loudness: candidate sound effects, beat hits, or emphasised words.

    A jump counts when the level rises `jump_db` above the median of the previous 200 ms.
    These are candidates; what each one is (whoosh, pop, a word) is labelled from context.
    """
    out: list[float] = []
    look = int(0.2 / hop_s)
    for i in range(look, len(env_db)):
        if env_db[i] < floor_db:
            continue
        base = float(np.median(env_db[i - look:i]))
        if env_db[i] - base >= jump_db:
            t = round(i * hop_s, 2)
            if not out or t - out[-1] > 0.15:
                out.append(t)
    return out


def extract_frame(path: Path, t: float, dest: Path, width: int = 540) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(t, 0):.3f}", "-i", str(path),
        "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", str(dest),
    ])
    if r.returncode != 0 or not dest.exists():
        log.warning("No frame at %.2fs in %s", t, path.name)
        return None
    return dest


def transcribe(path: Path, model_size: str = "small", language: str | None = None) -> dict | None:
    """Word-timed transcript with faster-whisper. Returns None if it isn't installed."""
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        log.warning("faster-whisper is not installed; transcripts will be missing")
        return None
    try:
        model = _whisper(model_size)
        segments, info = model.transcribe(str(path), word_timestamps=True, language=language, vad_filter=False)
        segments = list(segments)  # transcription runs lazily; run it here so errors land in this try
    except Exception as e:
        log.warning("Transcription failed for %s: %s", path.name, e)
        return None
    words, segs = [], []
    for s in segments:
        segs.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()})
        for w in s.words or []:
            words.append({"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word.strip(),
                          "p": round(w.probability, 2)})
    return {"language": info.language, "segments": segs, "words": words, "model": model_size}


_MODELS: dict = {}


def _whisper(size: str):
    from faster_whisper import WhisperModel

    if size not in _MODELS:
        _MODELS[size] = WhisperModel(size, device="auto", compute_type="int8")
    return _MODELS[size]
