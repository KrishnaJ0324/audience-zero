"""Tiny stdlib-only WAV synthesis + mixing.

Lets the ``mock`` audio path produce *real, audible* WAV files with zero
dependencies (no ffmpeg, no numpy). Distinct voices map to distinct timbres so
the multi-voice produced scene is audibly multi-voice on stage.
"""
from __future__ import annotations

import math
import struct
import wave

SR = 22050  # sample rate


def _tone(freq: float, dur: float, vol: float, harmonics: tuple[float, ...] = (1.0,)) -> list[float]:
    n = int(SR * dur)
    out = [0.0] * n
    for hi, hamp in enumerate(harmonics, start=1):
        f = freq * hi
        for i in range(n):
            out[i] += hamp * math.sin(2 * math.pi * f * (i / SR))
    # normalise by harmonic energy, apply short attack/decay envelope
    peak = sum(abs(h) for h in harmonics) or 1.0
    atk = int(SR * 0.01)
    dec = int(SR * 0.04)
    for i in range(n):
        env = 1.0
        if i < atk:
            env = i / max(atk, 1)
        elif i > n - dec:
            env = max(0.0, (n - i) / max(dec, 1))
        out[i] = (out[i] / peak) * vol * env
    return out


def voice_timbre(voice_id: str) -> tuple[float, tuple[float, ...]]:
    """Deterministic (base_freq, harmonic profile) per voice id."""
    base = 130.0 + (sum(ord(c) for c in voice_id) % 12) * 14.0  # 130..300 Hz
    profiles = [
        (1.0, 0.5, 0.25),
        (1.0, 0.3, 0.6, 0.2),
        (1.0, 0.7, 0.4, 0.15),
        (1.0, 0.2, 0.1),
    ]
    prof = profiles[sum(ord(c) for c in voice_id) % len(profiles)]
    return base, prof


def speak(text: str, voice_id: str) -> list[float]:
    """Render text as a short pseudo-speech gesture: one syllable-ish tone burst
    per word, pitch-modulated by the word so it feels like prosody."""
    base, prof = voice_timbre(voice_id)
    words = (text or "…").split()
    words = words[:36] or ["…"]
    samples: list[float] = []
    for w in words:
        wl = len(w)
        pitch = base * (1.0 + 0.12 * math.sin(len(samples) / 4000.0)) * (0.9 + (wl % 5) * 0.05)
        dur = min(0.34, 0.09 + wl * 0.02)
        samples += _tone(pitch, dur, 0.55, prof)
        samples += [0.0] * int(SR * 0.05)  # inter-word gap
    return samples


def music_bed(dur: float) -> list[float]:
    """Soft ambient pad (root + fifth) at low volume for ducking under voices."""
    n = int(SR * dur)
    root = _tone(110.0, dur, 0.10, (1.0, 0.4, 0.2))
    fifth = _tone(164.81, dur, 0.06, (1.0, 0.3))
    return [(root[i] if i < len(root) else 0.0) + (fifth[i] if i < len(fifth) else 0.0) for i in range(n)]


def sfx_blip() -> list[float]:
    return _tone(880.0, 0.12, 0.4, (1.0, 0.5, 0.3))


def _mix_into(base: list[float], overlay: list[float], at: int = 0) -> list[float]:
    end = at + len(overlay)
    if end > len(base):
        base = base + [0.0] * (end - len(base))
    for i, s in enumerate(overlay):
        base[at + i] += s
    return base


def write_wav(path: str, samples: list[float]) -> float:
    peak = max((abs(s) for s in samples), default=0.0)
    gain = 0.9 / peak if peak > 1.0 else 0.9 if peak > 0 else 0.0
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        frames = bytearray()
        for s in samples:
            v = int(max(-1.0, min(1.0, s * (gain if peak else 0.0))) * 32767)
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))
    return len(samples) / SR


def peaks(path: str, buckets: int = 400) -> list[float]:
    """Downsample a WAV into ``buckets`` normalized peak amplitudes (0..1) for a
    waveform display. Reads via the stdlib — no numpy/ffmpeg."""
    import struct as _struct

    with wave.open(path, "r") as w:
        n = w.getnframes()
        sw = w.getsampwidth()
        ch = w.getnchannels()
        raw = w.readframes(n)
    if sw != 2 or n == 0:
        return [0.0] * buckets
    total = len(raw) // 2
    vals = _struct.unpack("<" + "h" * total, raw)
    if ch > 1:
        vals = vals[::ch]  # take the first channel
    frames = len(vals)
    buckets = max(1, min(buckets, frames))
    step = frames / buckets
    out: list[float] = []
    for b in range(buckets):
        lo = int(b * step)
        hi = max(lo + 1, int((b + 1) * step))
        chunk = vals[lo:hi]
        peak = max((abs(v) for v in chunk), default=0) / 32767.0
        out.append(round(peak, 4))
    return out


def compose_scene(
    line_samples: list[list[float]],
    music: bool = True,
    sfx: bool = False,
) -> list[float]:
    """Sequence the spoken lines, duck a music bed underneath, optional SFX."""
    track: list[float] = []
    for i, ls in enumerate(line_samples):
        if sfx and i == 0:
            track += sfx_blip()
        track += ls
        track += [0.0] * int(SR * 0.15)
    dur = len(track) / SR if track else 1.0
    if music:
        track = _mix_into(track, music_bed(dur))
    return track
