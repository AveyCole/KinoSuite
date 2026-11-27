"""Lightweight, musical built-in KinoWave Studio showcase session (<0.2s generation)."""
from __future__ import annotations

import numpy as np

from .models import (
    AudioClip,
    AudioTrack,
    EffectSlot,
    KinoWaveProject,
    LabelItem,
    LabelTrack,
    MidiNote,
    NoteTrack,
    ProjectMetadata,
)


def create_sample_session(sample_rate: int = 48000) -> KinoWaveProject:
    """Create a fast-loading, musical 8-second stereo multitrack showcase project
    demonstrating waveforms, clips, real-time FX, labels, and MIDI notes."""
    sr = sample_rate
    proj = KinoWaveProject(name="KinoWave_Studio_Session.kwp", sample_rate=sr)
    proj.bpm = 120.0
    proj.time_sig_num = 4
    proj.time_sig_den = 4
    proj.show_beats_grid = True
    proj.metadata = ProjectMetadata(
        artist="KinoSuite Studio",
        title="KinoWave Showcase Session",
        album="KinoSuite Audio Demos",
        track_number="01",
        year="2026",
        genre="Electronic / Ambient",
        comments="32-bit float multitrack session — press Space to play!",
    )

    dur = 8.0
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float32) / sr

    # 1. Warm Stereo Pad Track (Cmaj9 -> Am9 progression)
    pad_l = np.zeros(n, dtype=np.float32)
    pad_r = np.zeros(n, dtype=np.float32)
    chords = [
        (0.0, 4.0, [130.81, 196.00, 246.94, 293.66, 329.63]),
        (4.0, 8.0, [110.00, 164.81, 220.00, 246.94, 329.63]),
    ]
    for s0, s1, freqs in chords:
        i0, i1 = int(s0 * sr), int(s1 * sr)
        tt = np.arange(i1 - i0, dtype=np.float32) / sr
        env = np.minimum(1.0, tt / 0.45) * np.minimum(1.0, (s1 - s0 - tt) / 0.55)
        sig_l = np.zeros_like(tt)
        sig_r = np.zeros_like(tt)
        for k, f in enumerate(freqs):
            detune = 1.0 + (k - 2) * 0.0018
            sig_l += np.sin(2.0 * np.pi * f * tt) * 0.14
            sig_r += np.sin(2.0 * np.pi * f * detune * tt + 0.4) * 0.14
        pad_l[i0:i1] += sig_l * env
        pad_r[i0:i1] += sig_r * env
    pad_tr = AudioTrack(name="Warm Analog Pad", channels=2, sample_rate=sr, color="#10D9A0", gain_db=-2.0)
    pad_tr.clips.append(AudioClip(samples=np.vstack([pad_l, pad_r]), sample_rate=sr, start_time=0.0, name="Cmaj9 -> Am9 Pad", color="#10D9A0"))
    pad_tr.realtime_effects.append(EffectSlot(effect_name="Bass and Treble", enabled=True, params={"bass_db": 2.0, "treble_db": 1.5, "volume_db": 0.0}))
    proj.tracks.append(pad_tr)

    # 2. Stereo Pluck Melody Track (two separate clips to demonstrate clip editing)
    arp_tr = AudioTrack(name="Crystal Pluck Arp", channels=2, sample_rate=sr, color="#22D3EE", gain_db=-3.0)
    notes_a = [(0.0, 523.25), (0.5, 659.25), (1.0, 783.99), (1.5, 987.77), (2.0, 783.99), (2.5, 659.25), (3.0, 587.33), (3.5, 659.25)]
    notes_b = [(0.0, 440.00), (0.5, 523.25), (1.0, 659.25), (1.5, 783.99), (2.0, 659.25), (2.5, 523.25), (3.0, 493.88), (3.5, 523.25)]
    for clip_idx, (c_start, nlist, cname, ccol) in enumerate([(0.0, notes_a, "Phrase A", "#22D3EE"), (4.0, notes_b, "Phrase B", "#38BDF8")]):
        cn = int(4.0 * sr)
        cl = np.zeros(cn, dtype=np.float32)
        cr = np.zeros(cn, dtype=np.float32)
        for j, (nt, freq) in enumerate(nlist):
            p0 = int(nt * sr)
            plen = min(int(0.48 * sr), cn - p0)
            tt = np.arange(plen, dtype=np.float32) / sr
            env = np.minimum(1.0, tt / 0.006) * np.exp(-tt * 7.5)
            tone = (0.65 * np.sin(2.0 * np.pi * freq * tt) + 0.25 * np.sin(4.0 * np.pi * freq * tt) + 0.1 * np.sin(6.0 * np.pi * freq * tt)) * env * 0.42
            pan_l = 0.78 if j % 2 == 0 else 0.42
            pan_r = 0.42 if j % 2 == 0 else 0.78
            cl[p0 : p0 + plen] += tone * pan_l
            cr[p0 : p0 + plen] += tone * pan_r
        arp_tr.clips.append(AudioClip(samples=np.vstack([cl, cr]), sample_rate=sr, start_time=c_start, name=cname, color=ccol))
    proj.tracks.append(arp_tr)

    # 3. Punchy Kick & Pulse Rhythm Track (Mono)
    rhy_n = int(8.0 * sr)
    rhy = np.zeros(rhy_n, dtype=np.float32)
    rng = np.random.default_rng(7)
    for beat in range(16):
        p0 = int(beat * 0.5 * sr)
        if beat % 2 == 0:  # Kick drum pitch drop
            klen = min(int(0.22 * sr), rhy_n - p0)
            tt = np.arange(klen, dtype=np.float32) / sr
            f_inst = 52.0 + 110.0 * np.exp(-tt * 38.0)
            phase = 2.0 * np.pi * np.cumsum(f_inst) / sr
            rhy[p0 : p0 + klen] += np.sin(phase) * np.exp(-tt * 14.0) * 0.62
        else:  # Crisp hi-hat tick
            hlen = min(int(0.06 * sr), rhy_n - p0)
            tt = np.arange(hlen, dtype=np.float32) / sr
            rhy[p0 : p0 + hlen] += rng.standard_normal(hlen).astype(np.float32) * np.exp(-tt * 95.0) * 0.16
    rhy_tr = AudioTrack(name="Studio Rhythm Pulse", channels=1, sample_rate=sr, color="#A78BFA", gain_db=-2.5)
    rhy_tr.clips.append(AudioClip(samples=rhy[None, :], sample_rate=sr, start_time=0.0, name="120 BPM Groove", color="#A78BFA"))
    proj.tracks.append(rhy_tr)

    # 4. Section Labels Track
    lbl_tr = LabelTrack(
        name="Arrangement Markers",
        labels=[
            LabelItem(start=0.0, end=4.0, text="Intro — Cmaj9"),
            LabelItem(start=4.0, end=8.0, text="Lift — Am9"),
        ],
    )
    proj.tracks.append(lbl_tr)

    # 5. MIDI Note Track (Bassline)
    midi_tr = NoteTrack(
        name="MIDI Synth Bass",
        mute=True,
        notes=[
            MidiNote(0.0, 1.8, 36, 100),
            MidiNote(2.0, 3.8, 43, 95),
            MidiNote(4.0, 5.8, 33, 105),
            MidiNote(6.0, 7.8, 40, 95),
        ],
    )
    proj.tracks.append(midi_tr)

    proj.set_selection(0.0, 4.0)
    proj.loop_start = 0.0
    proj.loop_end = 4.0
    proj.push_history("Opened KinoWave Studio Session")
    proj.dirty = False
    return proj
