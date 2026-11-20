"""Spatial mix of the Walk music: each shop's bar comes from its shop door.
One command:  python spatial_mix.py            -> walk_music_spatial.wav   (add --check to print the measurements)
Needs the stems:  WALK_STEMS=1 python make_walk_music.py   (walk_stem_*.wav).  The camera path is sampled once from walk3.blend
with a headless Blender run (cached in fx_logs/audio/cam_walk3.json). Method: numpy. (Blender Speaker objects + bpy.ops.sound.mixdown
were tried first: the headless mixdown renders only sequencer strips, the speakers give silence. See fx_logs/audio.md.)
Per shop bar k: gain follows the distance camera -> door (relative to the bar's own mean distance, soft-limited to +-4 dB),
pan follows the bearing of the door against the camera heading (head turns included), limited to +-0.55, constant power."""
import numpy as np, json, os, subprocess, sys
from scipy.io import wavfile
from scipy.ndimage import uniform_filter1d

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"
CAM = os.path.join(HERE, 'fx_logs', 'audio', 'cam_walk3.json')
GAIN_EXP = float(os.environ.get('SP_GAIN_EXP', 2.0))    # dB per dB of distance change (1.0 = free-field inverse distance)
GAIN_MAX = 4.0                                           # dB, soft limit
PAN_MAX = 0.55
PAN_WIDTH = float(os.environ.get('SP_PAN_WIDTH', 0.5))   # sin(bearing) at which the pan reaches 76% of PAN_MAX
SIDE = float(os.environ.get('SP_SIDE', 0.7))             # stereo width of the stem kept after panning (1 = untouched)
SMOOTH = 0.6                                             # s, moving average on gain and pan (crossfade time >= 0.4 s)
FPS = 24
# shop index in the video script SHOP_LIST: (cx, side, door_x); the camera looks at them in this bar order
SHOPS = {0: (-20, 'N', 0.0), 1: (-10, 'N', -2.8), 2: (0, 'N', 0.0), 3: (10, 'N', 2.8), 4: (20, 'N', -2.8),
         5: (-20, 'S', 2.8), 6: (-10, 'S', 0.0), 7: (0, 'S', -2.8), 8: (10, 'S', 2.8), 9: (20, 'S', 0.0)}
BAR_SHOP = [0, 5, 6, 1, 2, 7, 8, 3, 4, 9]      # bar 1..10 -> SHOP_LIST index (toy book ice candy cookie pet comic train bike arcade)
YS = -18.0


def door_xy(i):   # = lp(S, door_x, 0) of the video script
    cx, side, dx = SHOPS[i]
    return (cx + dx, 0.0) if side == 'N' else (cx - dx, YS)


def camera_path():
    if not os.path.exists(CAM):
        code = ("import bpy,json,mathutils as m;sc=bpy.context.scene;c=bpy.data.objects['Camera'];r=[]\n"
                "for f in range(1,1442):\n sc.frame_set(f);q=c.matrix_world.to_3x3();fw=q@m.Vector((0,0,-1));rt=q@m.Vector((1,0,0));p=c.matrix_world.translation;r.append([p.x,p.y,fw.x,fw.y,rt.x,rt.y])\n"
                "json.dump(r,open(%r,'w'))" % CAM)
        subprocess.run([BLENDER, '-b', os.path.join(HERE, 'walk3.blend'), '--python-expr', code], check=True, capture_output=True)
    return np.array(json.load(open(CAM)))     # row f-1: x, y, forward xy, right xy


def geometry(cam, i):
    """per frame: distance (m) and bearing (rad, left negative) of shop i's door."""
    dx, dy = door_xy(i)
    vx, vy = dx - cam[:, 0], dy - cam[:, 1]
    fwl = np.hypot(cam[:, 2], cam[:, 3])
    fw = (vx * cam[:, 2] + vy * cam[:, 3]) / fwl
    rt = (vx * cam[:, 4] + vy * cam[:, 5])
    return np.hypot(vx, vy), np.arctan2(rt, fw)


def smooth(a):
    return uniform_filter1d(a, max(1, int(SMOOTH * FPS)), mode='nearest')


def curves(cam, bars):
    """per shop bar: gain (linear) and pan per video frame (1441 values each)."""
    out = {}
    for k in range(1, 11):
        d, th = geometry(cam, BAR_SHOP[k - 1])
        a = int(round(bars[k]['start'])) - 1
        dref = d[a:a + 100].mean()                                        # the bar's own mean distance = "current level"
        db = -GAIN_EXP * 20 * np.log10(d / dref)
        db = GAIN_MAX * np.tanh(db / GAIN_MAX)
        pan = PAN_MAX * np.tanh(np.sin(th) / PAN_WIDTH)     # sin: continuous when the shop is behind (pan returns to the centre), no side flip
        out[k] = (10 ** (smooth(db) / 20), smooth(pan), db, pan, d, th)
    return out


def to_samples(v, n, sr):   # frame f (1-based) is at (f-1)/FPS s
    return np.interp(np.arange(n) / sr, (np.arange(len(v))) / FPS, v)


def load(name):
    sr, x = wavfile.read(os.path.join(HERE, name))
    return sr, x.astype(np.float64) / 32767.0


def place(x, g, p, w):
    """gain g and constant-power pan p on the mid of the stereo stem x; the side part is kept with width w."""
    m, s = (x[:, 0] + x[:, 1]) / 2, (x[:, 0] - x[:, 1]) / 2
    return np.stack([g * (m * np.sqrt(2) * np.cos((p + 1) * np.pi / 4) + w * s),
                     g * (m * np.sqrt(2) * np.sin((p + 1) * np.pi / 4) - w * s)], 1)


def mix(unity=False):
    meta = json.load(open(os.path.join(HERE, 'walk_stem_meta.json')))
    scale, T = meta['scale'], meta['T']
    bars = json.load(open(os.path.join(HERE, 'walk_beats.json')))['bars']
    cam = camera_path()
    cv = curves(cam, bars)
    sr, x = load('walk_stem_00.wav')
    n = len(x)
    acc = x / scale
    for k in range(1, 11):
        sr, x = load('walk_stem_%02d.wav' % k)
        x /= scale
        g = to_samples(cv[k][0], n, sr)
        p = to_samples(cv[k][1], n, sr)
        if unity:
            g, p = np.ones(n), np.zeros(n)
        acc += place(x, g, p, 1.0 if unity else SIDE)
    sr, nz = load('walk_stem_noise.wav')
    t = np.arange(n) / sr
    acc = np.tanh(1.3 * acc) / 1.3                      # same master chain as make_walk_music.py
    fade = np.clip(t / 1.2, 0, 1) * np.clip((T - t) / 2.8, 0, 1)
    y = (acc + nz / scale) * fade[:, None]
    y = y[:int(T * sr)]
    return y, sr, cv, bars


def write(y, path):
    wavfile.write(path, 44100, (y * 32767).astype('<i2'))


if __name__ == '__main__':
    y, sr, cv, bars = mix()
    y *= 0.89 / np.abs(y).max()
    write(y, os.path.join(HERE, 'walk_music_spatial.wav'))
    print('wrote walk_music_spatial.wav', len(y) / sr, 's, peak', float(np.abs(y).max()))
    if '--check' in sys.argv:
        sys.path.insert(0, os.path.join(HERE, 'fx_logs', 'audio'))
        import check_spatial
        check_spatial.run(y, sr, cv, bars)
