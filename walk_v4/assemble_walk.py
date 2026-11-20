"""Assemble the Walk video in Blender's sequencer (no EEVEE, no GPU lock needed).

blender -b -P assemble_walk.py -- --frames walk2_frames --audio walk_music.wav --out Walk_assembled_test.mp4
Options: --crf HIGH|PERC_LOSSLESS|MEDIUM|LOW or a number such as 14 (default HIGH), --first N --last N (frame range, default all),
         --beats walk_beats.json (13 bar markers; default: next to this script), --lufs -18 (target; use 0 to skip normalising)
The final encode and the mux are done by Blender (FFMPEG, H.264, AAC 192 kbps). ffmpeg is used only to MEASURE loudness.
"""
import sys, os, re, json, glob, wave, shutil, tempfile, subprocess, argparse
import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--frames", default=os.path.join(HERE, "walk2_frames"))
ap.add_argument("--audio", default=os.path.join(HERE, "walk_music.wav"))
ap.add_argument("--out", default=os.path.join(HERE, "Walk_assembled.mp4"))
ap.add_argument("--crf", default="HIGH")
ap.add_argument("--first", type=int)
ap.add_argument("--last", type=int)
ap.add_argument("--beats", default=os.path.join(HERE, "walk_beats.json"))
ap.add_argument("--lufs", type=float, default=-18.0)
a = ap.parse_args(argv)
frames_dir, audio, out = (os.path.abspath(p) for p in (a.frames, a.audio, a.out))

files = sorted(glob.glob(os.path.join(frames_dir, "f_*.png")))
nums = [int(re.search(r"f_(\d+)\.png", f).group(1)) for f in files]
assert nums == list(range(nums[0], nums[0] + len(nums))), "gap in frame numbers"
n0, n1 = nums[0], nums[-1]
first, last = a.first or n0, a.last or n1
print(f"frames {n0}..{n1} ({len(files)}), render {first}..{last}")

# --- pre-normalise the audio to the target loudness with one linear gain (numpy; ffmpeg only measures) ---
tmp = tempfile.mkdtemp(prefix="assemble_")
norm_wav = audio
if a.lufs:
    with wave.open(audio) as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        assert sw == 2, "expects 16-bit wav"
        x = np.frombuffer(w.readframes(n), "<i2").reshape(-1, ch).astype(np.float64) / 32768
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", audio, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    lufs = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1])
    gain = 10 ** ((a.lufs - lufs) / 20)
    y = x * gain
    print(f"audio {lufs} LUFS -> gain {20*np.log10(gain):.2f} dB, sample peak {np.abs(y).max():.3f}")
    assert np.abs(y).max() < 0.95
    norm_wav = os.path.join(tmp, "audio_norm.wav")
    with wave.open(norm_wav, "wb") as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(y, -1, 1) * 32767).round().astype("<i2").tobytes())

# --- build the sequencer scene ---
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps, sc.render.fps_base = 24, 1.0
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, 100
sc.frame_start, sc.frame_end = first, last
sc.view_settings.view_transform = "Standard"   # PNGs are sRGB display images: no tone mapping on top
sc.view_settings.look = "None"
se = sc.sequence_editor_create()
vs = se.strips.new_image("walk_frames", files[0], channel=1, frame_start=n0)
for f in files[1:]:
    vs.elements.append(os.path.basename(f))
ss = se.strips.new_sound("walk_music", norm_wav, channel=2, frame_start=n0)
print("video strip", vs.frame_final_start, vs.frame_final_end, "sound strip", ss.frame_final_start, ss.frame_final_end)
if ss.frame_final_end > last + 1:
    ss.frame_final_end = last + 1   # trim the tail (sound is 1441.0 frames long; strip end is exclusive)

if os.path.exists(a.beats):
    for b in json.load(open(a.beats))["bars"]:
        sc.timeline_markers.new(b["name"], frame=int(round(b["start"])))

print("markers", len(sc.timeline_markers), [m.frame for m in sc.timeline_markers])

# --- output: media_type VIDEO must come before file_format FFMPEG (Blender 5.x) ---
r = sc.render
r.image_settings.media_type = "VIDEO"
r.image_settings.file_format = "FFMPEG"
r.image_settings.color_mode = "RGB"
f = r.ffmpeg
f.format, f.codec = "MPEG4", "H264"
f.ffmpeg_preset = "GOOD"
if a.crf.isdigit():   # numeric x264 CRF, e.g. --crf 14
    f.constant_rate_factor, f.custom_constant_rate_factor = "CUSTOM", int(a.crf)
else:
    f.constant_rate_factor = a.crf
f.gopsize = 24
f.audio_codec, f.audio_bitrate, f.audio_channels, f.audio_mixrate = "AAC", 192, "STEREO", 48000
r.use_sequencer = True
r.use_file_extension = False
os.makedirs(os.path.dirname(out), exist_ok=True)
r.filepath = out
bpy.ops.render.render(animation=True)
shutil.rmtree(tmp, ignore_errors=True)
print("wrote", out, os.path.getsize(out))
