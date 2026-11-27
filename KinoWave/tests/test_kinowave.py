"""Comprehensive verification suite for KinoWave (DSP, I/O, Editing, Automation & GUI)."""
from __future__ import annotations

import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np
from PySide6.QtWidgets import QApplication

from kinowave.audio_io import (
    CrashRecoveryManager,
    KinoCloudAudioManager,
    export_audio_file,
    export_labels_txt,
    export_midi_file,
    find_ffmpeg,
    import_audio_file,
    import_labels_txt,
    import_midi_file,
    import_raw_audio,
    load_kwp,
    read_wav_native,
    save_kwp,
    write_wav_native,
)
from kinowave.automation import (
    MacroManager,
    NyquistInterpreter,
    PluginManager,
    PreferencesManager,
    run_performance_benchmark,
)
from kinowave.dsp import (
    EFFECT_REGISTRY,
    PresetManager,
    apply_dither,
    capture_noise_profile,
    compute_spectrogram_db,
    compute_spectrum,
    export_sample_data_text,
    find_beats,
    find_clipping,
    find_sounds_or_silences,
    find_zero_crossing,
    gen_chirp,
    gen_dtmf,
    gen_noise,
    gen_plucked,
    gen_rhythm_track,
    gen_risset_drum,
    gen_silence,
    gen_tone,
    generate_regular_interval_labels,
    import_sample_data_text,
    measure_rms,
    resample_audio,
    run_effect,
    wcag_contrast,
)
from kinowave.mainwindow import KinoWaveWindow
from kinowave.models import AudioClip, AudioTrack, EffectSlot, KinoWaveProject, LabelItem, MidiNote
from kinowave.sample_project import create_sample_session


def test_all_effects_and_generators() -> None:
    sr = 48000
    sig = gen_tone(sr, 0.5, "Sawtooth", 220.0, 0.7, channels=2)
    sig += gen_noise(sr, 0.5, "Pink", 0.05, channels=2)
    np_prof = capture_noise_profile(gen_noise(sr, 0.25, "White", 0.05, channels=2), sr)

    for name in EFFECT_REGISTRY:
        extra = {"noise_profile": np_prof, "control_audio": sig}
        out = run_effect(name, sig, sr, extra_ctx=extra)
        assert out.dtype == np.float32, f"{name} returned {out.dtype}"
        assert out.ndim == 2 and out.shape[0] == 2, f"{name} bad shape {out.shape}"
        assert np.all(np.isfinite(out)), f"{name} produced NaN/Inf"

    # Generators
    assert gen_chirp(sr, 0.3, channels=2).shape[0] == 2
    assert gen_dtmf(sr, "123*#", 0.4).shape[1] > 1000
    assert gen_silence(sr, 0.2).max() == 0.0
    assert gen_rhythm_track(sr, 120.0, 4, 2).shape[1] > sr
    assert gen_plucked(sr, 60, 0.5).shape[1] > 1000
    assert gen_risset_drum(sr, 100.0, 0.6).shape[1] > 1000
    assert "Stereo:" in measure_rms(sig)["summary"]

    # 384 kHz Float32 Resampling & Dither & Zero Crossing
    hi = resample_audio(sig[:, :4800], 48000, 384000, quality="High")
    assert hi.shape == (2, 38400)
    d16 = apply_dither(sig, 16, "Shaped")
    assert np.max(np.abs(d16)) <= 1.0
    zc = find_zero_crossing(sig, 2000)
    assert 0 <= zc < sig.shape[1]
    print(f"[PASS] All {len(EFFECT_REGISTRY)} effects, 7 generators, 384 kHz resample & dither verified.")


def test_analysis_tools() -> None:
    sr = 48000
    sig = gen_tone(sr, 1.0, "Sine", 1000.0, 0.9, channels=2)
    freqs, db = compute_spectrum(sig, sr)
    pk_hz = freqs[int(np.argmax(db[1:]) + 1)]
    assert 960.0 <= pk_hz <= 1040.0, f"Unexpected peak {pk_hz}"
    sdb, _ = compute_spectrogram_db(sig, sr)
    assert sdb.ndim == 2 and sdb.shape[0] > 10

    fg = gen_tone(sr, 0.5, "Sine", 440.0, 0.8)
    bg = gen_noise(sr, 0.5, "White", 0.02)
    wc = wcag_contrast(fg, bg)
    assert wc["wcag_pass"] is True

    clipped = np.clip(sig * 2.0, -1.0, 1.0)
    assert len(find_clipping(clipped, sr)) > 0
    rhy = gen_rhythm_track(sr, 120.0, 4, 2)
    assert len(find_beats(rhy, sr, 60.0)) >= 4
    assert len(find_sounds_or_silences(rhy, sr, "Sounds", -30.0, 0.02)) >= 1
    assert len(generate_regular_interval_labels(0.0, 10.0, 2.0)) == 6

    txt = export_sample_data_text(sig[:, :100], sr, fmt="CSV")
    imp = import_sample_data_text(txt)
    assert imp.shape == (2, 100)
    print("[PASS] Spectrum, Spectrogram, WCAG Contrast, Clipping, Beats, Sounds/Silences & Sample Data verified.")


def test_multitrack_editing_and_io() -> None:
    proj = create_sample_session(48000)
    assert len(proj.tracks) == 5
    orig_dur = proj.duration()
    assert orig_dur >= 7.9

    # Copy, Cut, Paste, Undo, Redo (with Sync-Lock enabled so audio + labels + MIDI ripple together)
    proj.sync_lock = True
    proj.set_selection(1.0, 2.0)
    clip_data = proj.copy_selection()
    proj.delete_range(1.0, 2.0, leave_gap=False)
    proj.push_history("Cut 1s")
    assert proj.audio_tracks()[0].duration() < orig_dur
    assert proj.duration() < orig_dur
    assert proj.undo()
    assert abs(proj.duration() - orig_dur) < 0.05
    assert proj.redo()
    proj.paste_clipboard(clip_data, 1.0, replace_selection=False)
    proj.push_history("Paste 1s")

    # Track ops: split stereo, swap, make stereo
    st = proj.audio_tracks()[0]
    proj.swap_stereo_channels(st)
    monos = proj.split_stereo_track(st, to_mono=True)
    assert len(monos) == 2
    rebuilt = proj.make_stereo_from_two_mono(monos[0], monos[1])
    assert rebuilt is not None and rebuilt.channels == 2

    # Mixdown with TimeTrack + MIDI NoteTrack
    tt = proj.add_time_track()
    tt.points = [(0.0, 1.0), (4.0, 1.25)]
    mix = proj.mix_render(0.0, 2.0, 48000)
    assert mix.shape[0] == 2 and mix.shape[1] > 40000

    with tempfile.TemporaryDirectory() as tmp:
        # Native .kwp round-trip
        kwp = os.path.join(tmp, "test.kwp")
        save_kwp(proj, kwp)
        loaded = load_kwp(kwp)
        assert len(loaded.tracks) == len(proj.tracks)

        # Native WAV 16/24/32f round-trip
        for depth in ("16-bit PCM", "24-bit PCM", "32-bit float"):
            wp = os.path.join(tmp, f"t_{depth[:2]}.wav")
            write_wav_native(wp, mix[:, :8000], 48000, bit_depth=depth)
            r_arr, r_sr = read_wav_native(wp)
            assert r_sr == 48000 and r_arr.shape == (2, 8000)

        # Raw import
        raw_p = os.path.join(tmp, "raw.pcm")
        mix[0, :2000].astype("<f4").tofile(raw_p)
        ra, rsr = import_raw_audio(raw_p, "32-bit float", "Little-endian", 1, 0, 48000)
        assert ra.shape == (1, 2000) and rsr == 48000

        # Labels .txt & MIDI .mid round-trips
        lb_p = os.path.join(tmp, "labels.txt")
        export_labels_txt(lb_p, [LabelItem(0.5, 1.5, "Chorus"), LabelItem(2.0, 2.0, "Drop")])
        assert len(import_labels_txt(lb_p)) == 2

        mid_p = os.path.join(tmp, "test.mid")
        export_midi_file(mid_p, [MidiNote(0.0, 0.5, 60, 100), MidiNote(0.5, 1.0, 64, 90)], bpm=120.0)
        m_notes = import_midi_file(mid_p)
        assert len(m_notes) == 2 and m_notes[0].pitch == 60

        # FFmpeg multi-format export & import if available
        if find_ffmpeg():
            for fmt, ext in [("FLAC", ".flac"), ("MP3", ".mp3"), ("OGG", ".ogg"), ("Opus", ".opus"), ("M4A (AAC)", ".m4a")]:
                ep = os.path.join(tmp, f"out{ext}")
                export_audio_file(ep, mix[:, :16000], 48000, fmt=fmt, target_sr=48000, metadata=proj.metadata)
                ia, isr, _ = import_audio_file(ep)
                assert ia.shape[1] > 4000 and isr >= 8000
            print("[PASS] FFmpeg export/import round-trip (FLAC, MP3, OGG, Opus, M4A) verified.")

        # Crash Recovery & Cloud Share
        rec = CrashRecoveryManager(tmp)
        rec.save_recovery(proj, "slot0")
        assert len(rec.list_recoverable()) == 1
        rec.clear_all()
        cloud = KinoCloudAudioManager(tmp)
        entry = cloud.publish_project(proj, notes="Test share")
        assert os.path.isfile(entry["share_html"])
    print("[PASS] Multitrack editing, .kwp, WAV, Raw, Labels, MIDI, Recovery & Cloud verified.")


def test_automation_nyquist_and_gui() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        prefs = PreferencesManager(tmp)
        sc_path = os.path.join(tmp, "sc.json")
        prefs.export_shortcuts(sc_path)
        assert len(prefs.import_shortcuts(sc_path)) > 20

        macros = MacroManager(tmp)
        sig = gen_tone(48000, 0.5, "Sine", 440.0, 0.4, channels=2)
        proc, logs = macros.run_on_audio("Podcast Voice Polish", sig, 48000)
        assert proc.shape == sig.shape and len(logs) >= 4

        ny = NyquistInterpreter()
        out, msg = ny.evaluate("(mult (sum (scale 0.5 (osc 60 0.5)) (scale 0.5 s)) (pwl 0.05 1.0 0.5 0.0))", sig, 48000)
        assert isinstance(out, np.ndarray) and out.shape[1] > 1000

        pm = PluginManager(tmp, tmp)
        assert len(pm.plugins) >= len(EFFECT_REGISTRY) + 2

        bench = run_performance_benchmark(48000, 1.0)
        assert "KinoWave DSP Score" in bench

    # Headless GUI & Rendering Smoothness Smoke Test
    app = QApplication.instance() or QApplication([])
    t0 = time.perf_counter()
    win = KinoWaveWindow(load_sample=True)
    win.show()
    app.processEvents()
    t_boot = (time.perf_counter() - t0) * 1000.0

    # Measure repaint speed (cached 60fps check)
    t_r0 = time.perf_counter()
    for i in range(10):
        win.canvas.playhead_s = i * 0.25
        win.canvas.repaint()
    t_rep = (time.perf_counter() - t_r0) * 1000.0 / 10.0

    # Test view modes & themes
    tr = win.current_project().audio_tracks()[0]
    for vm in ("Waveform", "Waveform (dB)", "Spectrogram", "Split View"):
        tr.view_mode = vm
        win.canvas.invalidate_caches()
        win.canvas.repaint()
    tr.view_mode = "Split View"
    win.canvas.invalidate_caches()
    win.canvas.repaint()

    for thm in ("Light", "High Contrast", "Dark"):
        win._apply_theme(thm)
        app.processEvents()

    # Save a preview screenshot in scratch for visual verification
    shot_dir = os.path.join(ROOT, ".kinowave_config")
    os.makedirs(shot_dir, exist_ok=True)
    shot_path = os.path.join(shot_dir, "preview_smoke.png")
    win.grab().save(shot_path)
    assert os.path.isfile(shot_path) and os.path.getsize(shot_path) > 10000

    # Test scripting pipe command handler
    rep = win._handle_pipe_command("GetInfo: Type=Tracks")
    assert "Tracks=5" in rep

    win.close()
    print(f"[PASS] GUI smoke test passed! Startup: {t_boot:.0f} ms | Avg playhead repaint: {t_rep:.1f} ms | Screenshot: {shot_path}")


if __name__ == "__main__":
    test_all_effects_and_generators()
    test_analysis_tools()
    test_multitrack_editing_and_io()
    test_automation_nyquist_and_gui()
    print("\nALL KINOWAVE VERIFICATION TESTS PASSED!")
