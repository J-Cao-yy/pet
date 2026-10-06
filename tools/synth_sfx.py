"""Synthesize the placeholder sound effects into ``assets/sounds/*.wav``.

Pure standard library (``wave`` / ``math`` / ``struct``), so it runs anywhere
and needs no audio dependency. Every key in ``betty_pet.audio.SOUND_KEYS``
gets a short synthesized motif — pleasant little sine chimes with a decay
envelope, one musical idea per event. Re-run after tweaking a motif:

    python tools/synth_sfx.py

The outputs are placeholders: swap in real recordings later by replacing the
WAVs (same names) without touching any code.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 22_050
MASTER_GAIN = 0.55  # headroom so stacked harmonics never clip

NOTE = {
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23,
    "G4": 392.00, "A4": 440.00, "B4": 493.88,
    "C5": 523.25, "D5": 587.33, "E5": 659.26, "F5": 698.46,
    "G5": 783.99, "A5": 880.00, "B5": 987.77, "C6": 1046.50,
    "C3": 130.81, "E3": 164.81, "G3": 196.00, "A3": 220.00, "B3": 246.94,
}

# Each motif is a list of (frequency_hz, duration_s, gain) — a frequency of 0
# is a rest. One musical idea per event: poke gets a tick, refusal gets a
# "womp womp", level-up gets a tiny fanfare, and so on.
MOTIFS: dict[str, list[tuple[float, float, float]]] = {
    "click": [(900.0, 0.06, 1.0)],
    "wave": [(NOTE["E5"], 0.09, 1.0), (0.0, 0.02, 0.0), (NOTE["A5"], 0.12, 1.0)],
    "feed": [(NOTE["G4"], 0.09, 1.0), (0.0, 0.04, 0.0), (NOTE["F4"], 0.11, 1.0)],
    "play": [(NOTE["C5"], 0.07, 1.0), (NOTE["E5"], 0.07, 1.0), (NOTE["G5"], 0.10, 1.0)],
    "rest": [(NOTE["E5"], 0.14, 0.9), (0.0, 0.03, 0.0), (NOTE["C5"], 0.18, 0.8)],
    "refuse": [(NOTE["B3"], 0.12, 1.0), (0.0, 0.05, 0.0), (NOTE["A3"], 0.16, 1.0)],
    "level_up": [
        (NOTE["C5"], 0.09, 1.0), (NOTE["E5"], 0.09, 1.0),
        (NOTE["G5"], 0.09, 1.0), (NOTE["C6"], 0.22, 1.1),
    ],
    "land": [(NOTE["C3"], 0.12, 1.2), (NOTE["E3"], 0.06, 0.6)],
    "perch": [(NOTE["C6"], 0.05, 0.9), (0.0, 0.03, 0.0), (NOTE["G5"], 0.09, 1.0)],
    "focus_start": [(NOTE["E5"], 0.12, 0.9), (NOTE["A5"], 0.16, 0.9)],
    "focus_done": [
        (NOTE["E5"], 0.10, 1.0), (NOTE["G5"], 0.10, 1.0), (NOTE["C6"], 0.24, 1.1),
    ],
}


def synth_note(freq: float, duration: float, gain: float) -> list[float]:
    """One note: sine + a soft 2nd harmonic, exponential decay envelope."""
    samples: list[float] = []
    n = int(SAMPLE_RATE * duration)
    decay = 5.0 / duration  # envelope speed scales with note length
    for i in range(n):
        t = i / SAMPLE_RATE
        envelope = math.exp(-decay * t) * min(1.0, i / (SAMPLE_RATE * 0.004))
        value = math.sin(2 * math.pi * freq * t)
        value += 0.35 * math.sin(4 * math.pi * freq * t)  # 2nd harmonic
        samples.append(gain * envelope * value / 1.35)
    return samples


def render(motif: list[tuple[float, float, float]]) -> list[float]:
    out: list[float] = []
    for freq, duration, gain in motif:
        if freq <= 0:
            out.extend([0.0] * int(SAMPLE_RATE * duration))
        else:
            out.extend(synth_note(freq, duration, gain))
    # 40 ms of trailing silence so fast successive plays don't click.
    out.extend([0.0] * int(SAMPLE_RATE * 0.04))
    return out


def write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = max((abs(s) for s in samples), default=0.0) or 1.0
    scale = MASTER_GAIN / peak if peak > MASTER_GAIN else 1.0
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s * scale)) * 32767))
            for s in samples
        )
        handle.writeframes(frames)


def main() -> int:
    for key, motif in MOTIFS.items():
        target = Path("assets/sounds") / f"{key}.wav"
        write_wav(target, render(motif))
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
