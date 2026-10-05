"""Generate celebration.wav, the trumpet fanfare played by the celebrate button

A short rising run, a held note that swells, then the final note, with the crackle of sparks in the sky
after each burst of the on-screen fireworks.

Run from this folder with: py make_celebration.py
"""

from __future__ import annotations

import functools
import math
import random
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 22050
# Loudest point of the trumpet as a fraction of full scale; the fireworks have their own FIREWORK_VOLUME
VOLUME = 0.045
# (frequency in Hz, start in seconds, length in seconds, loudness, swell)
# A swell note grows to full loudness over its length instead of starting at full strength.
# The line is kept to one lead trumpet with a single quiet harmony under the last two notes: stacked chords and a
# bass note are what made earlier versions sound thick and organ-like
NOTES = (
    # Build-up: a climbing run, each note louder than the last
    (261.63, 0.00, 0.12, 0.55, False),
    (329.63, 0.13, 0.12, 0.68, False),
    (392.00, 0.26, 0.12, 0.80, False),
    # Tension: a held note that swells into the final one
    (392.00, 0.39, 0.30, 0.90, True),
    (293.66, 0.39, 0.30, 0.22, True),
    # Arrival
    (523.25, 0.70, 0.95, 1.00, False),
    (392.00, 0.70, 0.95, 0.24, False),
)
HARMONIC_COUNT = 18
HIGHEST_HARMONIC_HZ = 9500
# How fast the harmonics fall away: a higher number is duller. Quiet notes use the mellow value, loud the bright
MELLOW_ROLLOFF = 1.9
BRIGHT_ROLLOFF = 0.55
BELL_HZ = 1700
BELL_WIDTH_HZ = 750
BELL_GAIN = 1.8
VIBRATO_HZ = 5.2
VIBRATO_DEPTH = 0.003
# Each note starts very slightly flat and slides up to pitch, as a tongued brass note does
SCOOP_DEPTH = 0.012
SCOOP_SECONDS = 0.018
# A short burst of breath at the start of each note gives it a defined edge
BREATH_LEVEL = 0.10
BREATH_SECONDS = 0.025
# When each firework bursts on screen; keep in step with FIREWORK_BURST_TIMES in ui_celebration.py
FIREWORK_BURST_TIMES = (0.0, 0.3, 0.55, 0.85, 1.1, 1.35, 1.6)
# Loudest point of a firework's crackle as a fraction of full scale, set separately from the trumpet
FIREWORK_VOLUME = 0.0252
FIREWORK_CRACKLE_DELAY = 0.0
FIREWORK_CRACKLE_SECONDS = 1.1
# Snaps per second when the crackle is at its busiest
FIREWORK_CRACKLE_RATE = 110.0


def envelope_at(elapsed: float, length: float, swell: bool) -> float:
    if swell:
        # Starts at the level the run ended on so there is no gap, then keeps growing
        growth = 0.4 + 0.6 * (elapsed / length) ** 1.5
        return growth * min(1.0, elapsed / 0.015) * min(1.0, (length - elapsed) / 0.015)
    # A tongued trumpet note: a sharp push to full strength, a quick settle, then a fade while held.
    # An even, unchanging level is what makes a tone sound like an organ
    attack = min(1.0, elapsed / 0.012)
    settle = 0.66 + 0.34 * math.exp(-max(0.0, elapsed - 0.012) / 0.045)
    fade = math.exp(-1.5 * max(0.0, elapsed - 0.18))
    release = min(1.0, (length - elapsed) / 0.05)
    return attack * settle * fade * release


@functools.lru_cache(maxsize=None)
def bell_resonance(frequency: float) -> tuple[float, ...]:
    """Boost for each harmonic of a note from the trumpet's bell, which rings strongest a little above 1 kHz"""
    return tuple(
        1 + BELL_GAIN * math.exp(-(((frequency * harmonic) - BELL_HZ) / BELL_WIDTH_HZ) ** 2)
        for harmonic in range(1, HARMONIC_COUNT + 1)
        if frequency * harmonic < HIGHEST_HARMONIC_HZ
    )


def brass(frequency: float, elapsed: float, length: float, swell: bool, breath: float) -> float:
    """One sample of a trumpet-like tone

    A trumpet has many strong harmonics, shaped by its bell, and they grow much stronger the harder it is blown:
    quiet notes are mellow and loud ones bright and buzzy. The harmonics here fall away quickly at low strength
    and slowly at full strength to follow that.
    """
    envelope = envelope_at(elapsed, length, swell)
    vibrato_ramp = min(1.0, max(0.0, elapsed - 0.3) / 0.3)
    vibrato = VIBRATO_DEPTH / (2 * math.pi * VIBRATO_HZ) * math.sin(2 * math.pi * VIBRATO_HZ * elapsed) * vibrato_ramp
    scoop = SCOOP_DEPTH * SCOOP_SECONDS * (math.exp(-elapsed / SCOOP_SECONDS) - 1)
    phase = 2 * math.pi * frequency * (elapsed + vibrato + scoop)
    rolloff = MELLOW_ROLLOFF - (MELLOW_ROLLOFF - BRIGHT_ROLLOFF) * envelope
    tone = 0.0
    for harmonic, boost in enumerate(bell_resonance(frequency), start=1):
        tone += harmonic**-rolloff * boost * math.sin(harmonic * phase)
    return (tone + breath * BREATH_LEVEL * math.exp(-elapsed / BREATH_SECONDS)) * envelope


def firework_crackle(noise: random.Random) -> list[float]:
    """The crackle of one firework's sparks in the sky after it has burst: no launch and no bang

    It is built from hundreds of tiny snaps, each a few thousandths of a second of noise. They come thick and
    fast just after the burst, then thin out and grow fainter as the sparks burn away
    """
    count = int(FIREWORK_CRACKLE_SECONDS * SAMPLE_RATE)
    samples = [0.0] * count
    elapsed = 0.0
    while True:
        # The snaps are thickest the instant the burst appears, then become rarer; the gaps between them are random
        busy = math.exp(-elapsed / 0.33)
        elapsed += noise.expovariate(max(FIREWORK_CRACKLE_RATE * busy, 4.0))
        if elapsed >= FIREWORK_CRACKLE_SECONDS:
            break
        # Most snaps are small, with the odd louder pop among them
        strength = noise.uniform(0.25, 0.6) if noise.random() < 0.85 else noise.uniform(0.7, 1.0)
        strength *= 0.35 + 0.65 * math.exp(-elapsed / 0.45)
        decay = noise.uniform(0.0015, 0.005) * SAMPLE_RATE
        first = int(elapsed * SAMPLE_RATE)
        # Lightly smoothed noise gives each snap some body, so it reads as a pop rather than a hiss
        grain = 0.0
        for offset in range(min(int(decay * 5), count - first)):
            grain += 0.32 * (noise.uniform(-1, 1) - grain)
            samples[first + offset] += strength * grain * math.exp(-offset / decay)
    # Taking away part of the previous sample strips out the low rumble, leaving the snaps crisp
    return [samples[0]] + [samples[index] - 0.6 * samples[index - 1] for index in range(1, count)]


def main() -> None:
    noise = random.Random(7)
    total = 0.05 + max(
        max(start + length for _frequency, start, length, _loudness, _swell in NOTES),
        FIREWORK_BURST_TIMES[-1] + FIREWORK_CRACKLE_DELAY + FIREWORK_CRACKLE_SECONDS,
    )
    samples = [0.0] * int(total * SAMPLE_RATE)
    for frequency, start, length, loudness, swell in NOTES:
        first = int(start * SAMPLE_RATE)
        for index in range(int(length * SAMPLE_RATE)):
            samples[first + index] += loudness * brass(frequency, index / SAMPLE_RATE, length, swell, noise.uniform(-1, 1))
    peak = max(abs(sample) for sample in samples)

    # The fireworks are mixed in after the fanfare's peak is measured, so adding them does not change its volume
    for burst_time in FIREWORK_BURST_TIMES:
        # Each firework is made afresh so no two sound identical
        crackle = firework_crackle(noise)
        # Scaled against the trumpet's peak here because the whole mix is brought to VOLUME by that peak below
        crackle_scale = FIREWORK_VOLUME / VOLUME * peak / max(abs(sample) for sample in crackle)
        # The crackle starts at the moment its burst appears on screen
        first = int((burst_time + FIREWORK_CRACKLE_DELAY) * SAMPLE_RATE)
        for index, sample in enumerate(crackle):
            if first + index < len(samples):
                samples[first + index] += crackle_scale * sample

    frames = b"".join(
        struct.pack("<h", max(-32767, min(32767, int(32767 * VOLUME * sample / peak)))) for sample in samples
    )
    with wave.open(str(Path(__file__).with_name("celebration.wav")), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(frames)


if __name__ == "__main__":
    main()
