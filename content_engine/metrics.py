"""Numbers computed from the measurements: shots, pacing, speech, sound."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

import numpy as np


@dataclass
class Shot:
    index: int
    start: float
    end: float

    @property
    def length(self) -> float:
        return round(self.end - self.start, 3)


def shots_from_cuts(cuts: list[float], duration: float) -> list[Shot]:
    bounds = [0.0] + [c for c in cuts if 0 < c < duration] + [duration]
    return [Shot(i + 1, round(bounds[i], 3), round(bounds[i + 1], 3)) for i in range(len(bounds) - 1)]


def _thirds(duration: float) -> list[tuple[float, float]]:
    d = duration / 3
    return [(0, d), (d, 2 * d), (2 * d, duration)]


def editing_metrics(shots: list[Shot], duration: float) -> dict:
    lengths = [s.length for s in shots]
    cuts = [s.start for s in shots[1:]]
    longest = max(shots, key=lambda s: s.length)
    shortest = min(shots, key=lambda s: s.length)
    per_third = []
    for a, b in _thirds(duration):
        n = sum(1 for c in cuts if a <= c < b)
        per_third.append(round(n / (b - a), 3) if b > a else 0)
    return {
        "shots": len(shots),
        "cuts": len(cuts),
        "cuts_per_second": round(len(cuts) / duration, 3) if duration else 0,
        "avg_shot_s": round(statistics.mean(lengths), 3),
        "median_shot_s": round(statistics.median(lengths), 3),
        "shortest_shot": {"shot": shortest.index, "start": shortest.start, "length_s": shortest.length},
        "longest_shot": {"shot": longest.index, "start": longest.start, "length_s": longest.length},
        "cuts_per_second_by_third": dict(zip(("start", "middle", "end"), per_third)),
        "time_to_first_cut_s": cuts[0] if cuts else None,
    }


_SENT_END = re.compile(r"[.!?]+$")


def speech_metrics(words: list[dict], duration: float, shots: list[Shot], pause_s: float = 0.3) -> dict:
    if not words:
        return {"spoken_words": 0, "note": "no speech found (or no transcript)"}
    total = len(words)
    speaking_span = words[-1]["end"] - words[0]["start"]
    wpm = round(total / (speaking_span / 60), 1) if speaking_span > 0 else None

    by_third = []
    for a, b in _thirds(duration):
        n = sum(1 for w in words if a <= w["start"] < b)
        by_third.append(round(n / ((b - a) / 60), 1) if b > a else 0)

    pauses = []
    for prev, nxt in zip(words, words[1:]):
        gap = round(nxt["start"] - prev["end"], 2)
        if gap >= pause_s:
            pauses.append({"after_word": prev["word"], "at": prev["end"], "length_s": gap})

    # Sentences, split on end punctuation in the transcript.
    sentences, cur = [], []
    for w in words:
        cur.append(w["word"])
        if _SENT_END.search(w["word"]):
            sentences.append(cur)
            cur = []
    if cur:
        sentences.append(cur)
    lens = [len(s) for s in sentences]
    longest = max(sentences, key=len)
    shortest = min(sentences, key=len)

    words_per_shot = [sum(1 for w in words if s.start <= w["start"] < s.end) for s in shots]
    talk_time = sum(w["end"] - w["start"] for w in words)
    return {
        "spoken_words": total,
        "time_to_first_word_s": words[0]["start"],
        "first_words": " ".join(w["word"] for w in words[:12]),
        "words_per_minute": wpm,
        "words_per_minute_by_third": dict(zip(("start", "middle", "end"), by_third)),
        "sentences": len(sentences),
        "avg_sentence_words": round(statistics.mean(lens), 1),
        "longest_sentence": " ".join(longest),
        "shortest_sentence": " ".join(shortest),
        "avg_words_between_cuts": round(statistics.mean(words_per_shot), 1) if words_per_shot else None,
        "pauses_over_0_3s": pauses,
        "share_of_runtime_with_speech": round(talk_time / duration, 3) if duration else None,
        "closing_line": " ".join(sentences[-1]),
    }


def audio_metrics(env_db: np.ndarray, hop_s: float, words: list[dict], transients: list[float],
                  cuts: list[float], silences: list[tuple[float, float | None]], duration: float) -> dict:
    if env_db.size == 0:
        return {"note": "no audio track"}
    t = np.arange(env_db.size) * hop_s
    in_word = np.zeros(env_db.size, dtype=bool)
    for w in words:
        in_word |= (t >= w["start"]) & (t < w["end"])
    voice = env_db[in_word]
    gaps = env_db[~in_word]
    voice_db = float(np.median(voice)) if voice.size else None
    gap_db = float(np.median(gaps)) if gaps.size else None

    def near(x: float, xs: list[float], tol: float = 0.06) -> bool:
        return any(abs(x - y) <= tol for y in xs)

    word_starts = [w["start"] for w in words]
    trans_out = [x for x in transients if not near(x, word_starts, 0.08)]
    cuts_on_hits = sum(1 for c in cuts if near(c, transients))
    first3 = [x for x in transients if x < 3]
    return {
        "median_level_while_talking_dbfs": round(voice_db, 1) if voice_db is not None else None,
        "median_level_between_words_dbfs": round(gap_db, 1) if gap_db is not None else None,
        "background_under_voice": (
            None if voice_db is None or gap_db is None else
            "likely music or room sound under the voice" if gap_db > -45 else "near-silent between words"
        ),
        "loudness_jumps": transients,
        "loudness_jumps_not_on_a_word": trans_out,
        "loudness_jumps_in_first_3s": first3,
        "cuts_landing_on_a_loudness_jump": f"{cuts_on_hits} of {len(cuts)}",
        "silences_over_0_25s": [{"start": s, "end": e} for s, e in silences],
        "note": ("Loudness jumps are candidates for sound effects, beat hits or punched words. "
                 "The type of each sound can't be heard by the analysis model; it is labelled from "
                 "what's on screen at that moment, and marked as unconfirmed."),
    }


def hook_frame_times(duration: float) -> list[float]:
    return [t for t in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0) if t < duration]


def plan_frames(shots: list[Shot], duration: float, max_frames: int = 90) -> list[float]:
    """Frames to show Claude: the hook every 0.5 s, then the start and middle of each shot,
    then the last moment (for the loop check). Long shots get one frame per 2 s so zooms show."""
    times = set(hook_frame_times(duration))
    for s in shots:
        times.add(round(min(s.start + 0.05, s.end), 2))
        if s.length > 0.6:
            times.add(round(s.start + s.length / 2, 2))
        if s.length > 4:
            t = s.start + 2
            while t < s.end - 0.5:
                times.add(round(t, 2))
                t += 2
    times.add(round(max(duration - 0.1, 0), 2))
    # Drop frames within 0.15 s of one already kept (hook frames win).
    hook = set(hook_frame_times(duration))
    ordered: list[float] = []
    for t in sorted(times, key=lambda t: (t not in hook, t)):
        if all(abs(t - k) >= 0.15 for k in ordered):
            ordered.append(t)
    ordered.sort()
    if len(ordered) <= max_frames:
        return ordered
    # Keep every hook frame and the end; thin the rest evenly.
    keep = set(hook_frame_times(duration)) | {ordered[-1]}
    rest = [t for t in ordered if t not in keep]
    step = len(rest) / (max_frames - len(keep))
    thinned = [rest[int(i * step)] for i in range(max_frames - len(keep))]
    return sorted(keep | set(thinned))
