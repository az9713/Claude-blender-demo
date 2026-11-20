"""Sound design for the Walk video, all numpy. One command:  python sfx_mix.py   (add --check to run fx_logs/sfx/check_sfx.py after)

Input  : walk_music_spatial.wav (16 bit stereo 44.1 kHz), moments.json, walk_beats.json, fx_logs/audio/cam_walk3.json (cached camera path),
         finale.json (optional: {"title_frame": N}; if it is missing the chime is skipped).
Output : walk_music_final.wav   = music (ducked 1.5 dB under each signature sound) + signature sounds + street bed
         walk_sfx_sig.wav       = the signature sounds and the finale chime alone (as added to the mix, 16 bit)
         walk_sfx_beds.wav      = footsteps + crowd murmur alone (as added to the mix, 16 bit)
         fx_logs/sfx/sfx_only.wav = sig + beds, for a quick listen without the music
Rules  : mix = music * duck * h + (sig + beds) * gm.  No master limiter, no re-normalising: outside the effect windows the music keeps its own samples.
         Where the sum would pass 29162/32767 (0.88999, the peak of the input file): inside a window the music gets a short extra dip h (4 ms, smooth),
         outside a window the street bed is lowered (gm).
Options: --finale PATH (other finale.json), --outdir DIR (write everything flat into DIR instead of the project folder, for tests)."""
import numpy as np, json, os, sys, hashlib
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, hilbert
from scipy.ndimage import minimum_filter1d, uniform_filter1d

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SR, FPS, SEED = 44100, 24, 20261119
CAP = 29162.4                  # int16 units: after rounding the mix stays <= 29162 = 0.88999 (the input's own peak)
LEVEL_DB = -5.0                # signature sound peak against the music's local peak (input music, window onset .. onset + 0.5 s). Was -8.0 (6 to 9 dB rule); raised 3 dB for audibility, see fx_logs/sfx/log.md
LEVEL_ADJ = {'music_box_ting': +0.5, 'page_flutter': +1.9, 'scoop_plop': +0.5, 'sparkle_jar': -0.2, 'oven_ding': +0.9, 'bubble_pop': -1.5,
             'pow_hit': -0.3, 'train_toot': -1.7, 'bike_bell': -3.2, 'coin_blip': -4.2}   # dB on top of LEVEL_DB. Net change against the old build (-8.0 + old trim): toy +3.5, book +4.5, ice +3.1, candy +3.5, cookie +3.5, pet +1.5, comic +2.7, train +2.0, bike +0.5, coin -0.5. The tonal sounds that are already loud in the phone band (600 to 5000 Hz) got the small raises; the noisy / quiet-band ones got the large ones. pow_hit and scoop_plop are limited by the music dip (the sum must stay under 0.89)
REPEAT_DB = -3.5               # the repeat copy against the first (was -6.0)
DUCK_DB, DUCK_DB_SMALL = 1.5, 1.0   # signature sounds / repeats and chime
FOOT_DB, CROWD_DB = -30.0, -34.0    # bed RMS (whole file, both channels) against the RMS of the input music
CHIME_PEAK, CHIME_MAX_REL_DB = 0.10, -6.0
REPEATS = ('toy', 'ice', 'candy', 'bike', 'arcade')
FADE_IN, FADE_OUT = 0.006, 0.010
WIDTH = 0.30                   # side signal (Hilbert transform of the mid, uncorrelated with it) as a fraction of the mid


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


# ---------------------------------------------------------------------------------------------- synthesis helpers
def tt(d):
    return np.arange(int(round(d * SR))) / SR


def mid(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def ramp(t, a):
    return np.clip(t / a, 0, 1)


def bell(f, dur, tau, parts, att=0.002):
    t = tt(dur)
    return sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / (tau * k)) for r, a, k in parts) * ramp(t, att)


def put(buf, sig, t0, g=1.0):
    i = int(round(t0 * SR))
    n = min(len(sig), len(buf) - i)
    buf[i:i + n] += g * sig[:n]


def bpnoise(n, lo, hi, rng):
    return sosfilt(butter(2, [lo / (SR / 2), hi / (SR / 2)], 'band', output='sos'), rng.normal(0, 1, n))


def softclip(x, k):
    return np.tanh(k * x / np.abs(x).max()) / np.tanh(k)


def sweep_phase(f):
    return 2 * np.pi * np.cumsum(f) / SR


def square_bl(f, t, fmax=7000):   # band-limited square (odd harmonics), no aliasing
    return sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, int(fmax / f) + 1, 2))


# ---------------------------------------------------------------------------------------------- the ten signature sounds (mono, before fade)
# MIDI numbers: G6 91, C7 96, E7 100, A5 81, C6 84, D6 86, B6 95, D7 98, G7 103, E6 88, F6 89, Bb4 70, F5 77, A5 81, Bb5 82, E5 76, C#6 85
def music_box_ting(rng):   # C major chord tones G6 + C7, two tines
    buf = np.zeros(int(0.5 * SR))
    parts = ((1, 1, 1), (2, .25, .45), (3, .10, .25), (4, .05, .15))
    put(buf, bell(mid(91), 0.5, 0.20, parts), 0.0, 1.0)
    put(buf, bell(mid(96), 0.43, 0.17, parts), 0.07, 0.65)
    return buf


def page_flutter(rng):     # twelve paper flaps, speeding up then slowing, plus a soft swish; noise band 1.5 to 6 kHz
    n = int(0.45 * SR)
    env = np.zeros(n)
    t = tt(0.1)
    for j, ft in enumerate([0.0, .030, .058, .084, .108, .130, .150, .170, .192, .218, .248, .282]):
        put(env, np.exp(-t / 0.007) * ramp(t, 0.001), ft, (1.0 if j == 0 else 0.75) * 0.93 ** j * rng.uniform(0.85, 1.15))
    tn = tt(0.36)
    swish = np.sin(np.pi * np.clip(tn / 0.36, 0, 1)) ** 2 * 0.22
    put(env, swish, 0.0, 1.0)
    return softclip(bpnoise(n, 1500, 6000, rng) * env, 2.5)


def scoop_plop(rng):       # Fmaj9 tones: a water plop rising to A5, a small second plop to C6, a little splash
    n = int(0.3 * SR)
    buf = np.zeros(n)
    for t0, fe, a, tau in ((0.0, mid(81), 1.0, 0.09), (0.11, mid(84), 0.45, 0.06)):
        t = tt(0.19)
        f = fe * (1 - 0.3 * np.exp(-t / 0.012))
        ph = sweep_phase(f)
        put(buf, (np.sin(ph) + 0.15 * np.sin(2 * ph)) * np.exp(-t / tau) * ramp(t, 0.001), t0, a)
    t = tt(0.03)
    put(buf, bpnoise(len(t), 2000, 5500, rng) * np.exp(-t / 0.008) * ramp(t, 0.0008), 0.0, 0.18)
    return buf


def sparkle_jar(rng):      # G69 tones: lid pop, then a rising glockenspiel sparkle G6 B6 D7 G7 and a falling tail E7 D7 G7
    buf = np.zeros(int(0.6 * SR))
    t = tt(0.04)
    pop = np.sin(sweep_phase(700 * (1 - 0.5 * t / 0.04))) * np.exp(-t / 0.012) * 0.5
    put(buf, pop + bpnoise(len(t), 800, 4500, rng) * np.exp(-t / 0.008) * 0.35 * ramp(t, 0.001), 0.0, 1.0)
    parts = ((1, 1, 1), (2, .2, .4), (4, .06, .2))
    for t0, m, a in ((0.040, 91, .85), (0.095, 95, .75), (0.150, 98, .65), (0.205, 103, .55), (0.285, 100, .38), (0.335, 98, .30), (0.395, 103, .24)):
        put(buf, bell(mid(m), 0.25, 0.11, parts), t0, a)
    return buf


def oven_ding(rng):        # Cmaj9 tone G6, one clear bell with a slightly detuned twin for a slow shimmer
    parts = ((1, 1, 1), (2, .2, .5), (2.76, .10, .3), (5.4, .04, .15))
    f = mid(91)
    return bell(f, 0.6, 0.22, parts) + 0.5 * bell(f * 1.003, 0.6, 0.22, parts)


def bubble_pop(rng):       # Dm9 tones: two bubbles rising to D6 and F6, a pop click
    buf = np.zeros(int(0.2 * SR))
    for t0, fe, a in ((0.0, mid(86), 1.0), (0.06, mid(89), 0.5)):
        t = tt(0.12)
        f = fe * (1 - 0.3 * np.exp(-t / 0.008))
        put(buf, np.sin(sweep_phase(f)) * (np.exp(-t / 0.04)) * ramp(t, 0.001), t0, a)
    t = tt(0.01)
    put(buf, bpnoise(len(t), 1500, 5500, rng) * np.exp(-t / 0.003) * ramp(t, 0.0006), 0.0, 0.25)
    return buf


def pow_hit(rng):          # noise burst 0.5 to 5.5 kHz, a falling body Bb4 to Bb3, a chip stab F5 + Bb5 (Bbmaj7#11 tones)
    n = int(0.35 * SR)
    buf = np.zeros(n)
    t = tt(0.3)
    burst = bpnoise(len(t), 500, 5500, rng) * np.exp(-t / 0.07) * ramp(t, 0.0015)
    body = np.sin(sweep_phase(mid(70) * (0.5 + 0.5 * np.exp(-t / 0.06)))) * np.exp(-t / 0.09) * ramp(t, 0.001)
    put(buf, softclip(burst, 2.5) * 0.9 + 0.8 * body, 0.0, 1.0)
    ts = tt(0.14)
    stab = (square_bl(mid(77), ts, 5000) + 0.8 * square_bl(mid(82), ts, 5000)) * np.exp(-ts / 0.06) * ramp(ts, 0.002) * 0.25
    put(buf, stab, 0.02, 1.0)
    return buf


def train_toot(rng):       # A7 tones: a three-reed steam whistle A5 + E5 + C#6, scoops up into pitch, light vibrato, breath
    n = int(0.5 * SR)
    t = tt(0.5)
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * ramp(t, 0.12)
    scoop = 1 - 0.03 * np.exp(-t / 0.03)
    s = np.zeros(n)
    for m, a in ((81, 1.0), (76, 0.7), (85, 0.45)):
        ph = sweep_phase(mid(m) * scoop * vib)
        s += a * (np.sin(ph) + 0.12 * np.sin(2 * ph))
    env = ramp(t, 0.015) * np.where(t < 0.32, 1.0, 0.5 + 0.5 * np.cos(np.pi * np.clip((t - 0.32) / 0.18, 0, 1)))
    return (s + 0.07 * bpnoise(n, 2000, 5000, rng)) * env


def bike_bell(rng):        # G9 tones: G6 with its fifth D7, four quick strikes (a trill), ringing out
    buf = np.zeros(int(0.6 * SR))
    parts = ((1, 1, 1), (1.5, .45, .8), (2, .2, .5), (2.76, .12, .3))
    for t0, a in ((0.0, 1.0), (0.06, .72), (0.12, .55), (0.18, .40)):
        put(buf, bell(mid(91), 0.6 - t0, 0.25, parts, att=0.0015), t0, a)
    return buf


def coin_blip(rng):        # D9 tones: A5 then D6, band-limited square, 8-bit steps
    buf = np.zeros(int(0.3 * SR))
    t1, t2 = tt(0.07), tt(0.23)
    n1 = square_bl(mid(81), t1) * ramp(t1, 0.002) * np.clip((0.07 - t1) / 0.004, 0, 1)
    n2 = square_bl(mid(86), t2) * ramp(t2, 0.002) * np.exp(-t2 / 0.11)
    put(buf, n1, 0.0, 0.85)
    put(buf, n2, 0.07, 1.0)
    return np.round(buf / np.abs(buf).max() * 63) / 63


def finale_chime(rng):     # C6 then G6 (Cmaj9 tones), soft bell
    buf = np.zeros(int(0.6 * SR))
    parts = ((1, 1, 1), (2, .2, .5), (3, .06, .3))
    put(buf, bell(mid(84), 0.6, 0.20, parts), 0.0, 1.0)
    put(buf, bell(mid(91), 0.47, 0.20, parts), 0.13, 0.8)
    return buf


SOUNDS = {'music_box_ting': music_box_ting, 'page_flutter': page_flutter, 'scoop_plop': scoop_plop, 'sparkle_jar': sparkle_jar,
          'oven_ding': oven_ding, 'bubble_pop': bubble_pop, 'pow_hit': pow_hit, 'train_toot': train_toot, 'bike_bell': bike_bell,
          'coin_blip': coin_blip}


def to_stereo(m, pan, place):
    """mono -> stereo with a little width and the spatial-mix pan; fades of 6 ms in and 10 ms out (exact zero at both ends)."""
    s = WIDTH * np.imag(hilbert(m))
    n = len(m)
    w = np.ones(n)
    a, b = int(FADE_IN * SR), int(FADE_OUT * SR)
    w[:a] = 0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a)
    w[-b:] = 0.5 + 0.5 * np.cos(np.pi * (np.arange(b) + 1) / b)
    w[-1] = 0.0
    return place(np.stack([m + s, m - s], 1) * w[:, None], 1.0, pan, 1.0)


# ---------------------------------------------------------------------------------------------- street bed
def footsteps(n, rng, place):
    out = np.zeros((n, 2))
    j = 0
    while True:
        fr = 8.5 + 12.5 * j                      # the beat grid of walk_beats.json (beat0 = 8.5 + 5 x 12.5 = 71)
        i0 = int(np.rint((fr - 1) / FPS * SR))
        if i0 > n - int(0.14 * SR):
            break
        jit = rng.uniform(0.85, 1.2)
        t = tt(0.13)
        s = bpnoise(len(t), 250 * jit, 1600 * jit, rng) * np.exp(-t / 0.022) * ramp(t, 0.003)
        s = s / np.abs(s).max() + 0.5 * np.sin(2 * np.pi * 105 * t) * np.exp(-t / 0.035) * ramp(t, 0.004)
        s *= rng.uniform(0.8, 1.2) * (0.5 - 0.5 * np.cos(np.pi * np.clip((0.13 - t) / 0.01, 0, 1)))
        st = place(np.stack([s, s], 1), 1.0, -0.10 if j % 2 == 0 else 0.10, 1.0)    # alternate L / R slightly
        out[i0:i0 + len(st)] += st
        j += 1
    return out


def lowrate(n, rate, fc, rng):   # slow random control curve, unit std, sampled at `rate`, low-passed at fc, interpolated to SR
    m = int(n / SR * rate) + 4
    x = sosfilt(butter(2, fc / (rate / 2), output='sos'), rng.normal(0, 1, m))
    x = x[int(rate):]
    x = x / x.std()
    return np.interp(np.arange(n) / SR, np.arange(len(x)) / rate, x)


def murmur(n, rng):              # filtered-noise babble: five formant-like bands, each with its own 3 to 5 Hz syllable swell, slow level drift
    out = np.zeros((n, 2))
    for c in range(2):
        acc = np.zeros(n)
        for fc, q, amp in ((280, 1.2, 1.0), (520, 1.5, .9), (900, 1.5, .7), (1500, 1.5, .4), (2300, 1.5, .2)):
            bw = fc / q
            mod = np.clip(1 + 0.6 * lowrate(n, 100, rng.uniform(3, 5), rng), 0.15, None)
            acc += amp * bpnoise(n, fc - bw / 2, fc + bw / 2, rng) * mod
        out[:, c] = acc * 10 ** (2.0 * lowrate(n, 20, 0.15, rng) / 20)
    return out


def rms(x):
    return float(np.sqrt((x.astype(np.float64) ** 2).mean()))


def duck_curve(depth_db, att=0.010, hold=0.2, rel=0.06):
    a, h, r = int(att * SR), int(hold * SR), int(rel * SR)
    w = np.concatenate([0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a), np.ones(h - a), 0.5 + 0.5 * np.cos(np.pi * np.arange(r) / r)])
    return 1 - (1 - 10 ** (-depth_db / 20)) * w


# ---------------------------------------------------------------------------------------------- build
def build(finale_path, quiet=False):
    import spatial_mix as sm
    if not os.path.exists(sm.CAM):
        sys.exit('missing %s: run python spatial_mix.py once (it needs Blender for that cache); sfx_mix.py does not start Blender' % sm.CAM)
    rng = np.random.default_rng(SEED)
    sr, music = wavfile.read(os.path.join(HERE, 'walk_music_spatial.wav'))
    assert sr == SR and music.ndim == 2 and music.dtype == np.int16
    n = len(music)
    M = music.astype(np.float64)                 # int16 units
    mf = M / 32767.0
    moments = json.load(open(os.path.join(HERE, 'moments.json')))['shops']
    bars = json.load(open(os.path.join(HERE, 'walk_beats.json')))['bars']
    cv = sm.curves(sm.camera_path(), bars)
    pan_at = lambda k, fr: float(cv[k][1][int(np.clip(fr, 1, 1441)) - 1])
    onset = lambda fr: int(np.rint((fr - 1) / FPS * SR))
    local_peak = lambda i0: float(np.abs(mf[i0:i0 + SR // 2]).max())

    events = []
    for k, s in enumerate(moments, 1):
        events.append(dict(name=s['sfx'], shop=s['shop'], bar=k, frame=s['hit'], kind='hit', rel_db=0.0, duck=DUCK_DB))
        if s['shop'] in REPEATS:
            events.append(dict(name=s['sfx'], shop=s['shop'], bar=k, frame=s['hit'] + 25, kind='repeat', rel_db=REPEAT_DB, duck=DUCK_DB_SMALL))
    finale = None
    if os.path.exists(finale_path):
        finale = json.load(open(finale_path))
        events.append(dict(name='finale_chime', shop='finale', bar=0, frame=int(finale['title_frame']), kind='chime', rel_db=0.0, duck=DUCK_DB_SMALL))

    sig = np.zeros((n, 2))
    dg = np.ones(n)
    info = []
    for e in events:
        i0 = onset(e['frame'])
        m = (finale_chime if e['kind'] == 'chime' else SOUNDS[e['name']])(rng)
        pan = 0.0 if e['kind'] == 'chime' else pan_at(e['bar'], e['frame'])
        st = to_stereo(m, pan, sm.place)
        P = local_peak(i0)
        if e['kind'] == 'chime':
            peak = min(CHIME_PEAK, P * 10 ** (CHIME_MAX_REL_DB / 20))
        else:
            peak = P * 10 ** ((LEVEL_DB + LEVEL_ADJ.get(e['name'], 0.0) + e['rel_db']) / 20)
        st *= peak / np.abs(st).max()
        assert i0 + len(st) <= n, 'sound runs past the end of the file'
        d = duck_curve(e['duck'])
        # polarity: keep the one that leaves less of the sum above the cap (its peaks then do not meet the music's peaks)
        ml = M[i0:i0 + len(st)] * d[:len(st), None] if len(d) >= len(st) else M[i0:i0 + len(st)] * np.concatenate([d, np.ones(len(st) - len(d))])[:, None]
        over = [np.maximum(np.abs(ml + sgn * st * 32767.0) - CAP, 0).sum() for sgn in (1, -1)]
        e['polarity'] = 1 if over[0] <= over[1] else -1
        st *= e['polarity']
        sig[i0:i0 + len(st)] += st
        dg[i0:i0 + len(d)] *= d
        e.update(i0=i0, pan=pan, local_peak=P, peak=peak, length=len(st) / SR)
        info.append(e)

    # street bed
    t = np.arange(n) / SR
    T = n / SR
    fade = np.clip(t / 1.2, 0, 1) * np.clip((T - t) / 2.8, 0, 1)            # the music's own fade
    mrms = rms(mf)
    foot = footsteps(n, rng, sm.place) * fade[:, None]
    foot *= mrms * 10 ** (FOOT_DB / 20) / rms(foot)
    crowd = murmur(n, rng) * fade[:, None]
    crowd *= mrms * 10 ** (CROWD_DB / 20) / rms(crowd)
    bed = foot + crowd

    # Overs. The mix must stay <= CAP (the input's own peak, 29162).  Inside an effect window the music gets a short extra dip (smooth, 4 ms,
    # a few tenths of a dB, only where music + added would pass CAP), so the signature sound keeps its designed level.  Outside the windows the
    # music is never touched; there only the added layer (street bed) is lowered where it would push the music's own peak over CAP.
    win = np.zeros(n, bool)
    for e in info:
        win[e['i0']:e['i0'] + int(max(e['length'], 0.26) * SR) + 441] = True
    md = M * dg[:, None]
    A = (sig + bed) * 32767.0
    W = 2 * int(0.004 * SR) + 1
    smooth_min = lambda v: uniform_filter1d(minimum_filter1d(v, W), W)       # <= v everywhere: min filter first, then an average of equal width

    def limit_gain(base, other, mask):   # largest gain g in [0, 1] on `base` with |g * base + other| <= CAP, per sample, where mask; min over channels
        g = np.ones(base.shape)
        over = (np.abs(base + other) > CAP) & mask[:, None]
        with np.errstate(divide='ignore', invalid='ignore'):
            need = np.where(base > 0, (CAP - other) / base, (-CAP - other) / base)
        g[over] = np.clip(need[over], 0, 1)
        return g.min(1)

    h = limit_gain(md, A, win)
    if (h < 1).any():
        h = np.where(win, smooth_min(h), 1.0)
        edge, m = np.ones(n), int(0.002 * SR)          # the extra dip fades in and out over 2 ms at the window edges (no gain step at the onset)
        r = 0.5 - 0.5 * np.cos(np.pi * np.arange(m) / m)
        for e in info:
            a = e['i0']
            b = a + int(max(e['length'], 0.26) * SR) + 441
            edge[a:a + m] = np.minimum(edge[a:a + m], r)
            edge[b - m:b] = np.minimum(edge[b - m:b], r[::-1])
        h = 1 - (1 - h) * edge
    md = md * h[:, None]
    gm = limit_gain(A, md, ~win)
    if (gm < 1).any():
        gm = np.where(~win, smooth_min(gm), 1.0)
    A_applied = A * gm[:, None]
    mix = np.clip(np.rint(md + A_applied), -CAP, CAP).astype(np.int16)
    stats = dict(music_dip_samples=int((h < 0.9999).sum()), music_dip_db=float(20 * np.log10(h.min())), bed_dip_samples=int((gm < 0.9999).sum()),
                 bed_dip_min=float(gm.min()), peak=int(np.abs(mix).max()), clipped_by_final_clip=int((np.abs(np.rint(md + A_applied)) > CAP).sum()))

    sig_i = np.rint(sig * 32767.0 * gm[:, None]).astype(np.int16)
    bed_i = np.rint(bed * 32767.0 * gm[:, None]).astype(np.int16)
    both = np.clip(sig_i.astype(np.int32) + bed_i, -32767, 32767).astype(np.int16)
    return mix, sig_i, bed_i, both, info, stats, finale, dict(music_rms=mrms, foot_rms=rms(foot), crowd_rms=rms(crowd))


if __name__ == '__main__':
    outdir = arg('--outdir')
    finale_path = arg('--finale', os.path.join(HERE, 'finale.json'))
    mix, sig_i, bed_i, both, info, stats, finale, lv = build(finale_path)
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        paths = [os.path.join(outdir, f) for f in ('walk_music_final.wav', 'walk_sfx_sig.wav', 'walk_sfx_beds.wav', 'sfx_only.wav')]
    else:
        os.makedirs(os.path.join(HERE, 'fx_logs', 'sfx'), exist_ok=True)
        paths = [os.path.join(HERE, 'walk_music_final.wav'), os.path.join(HERE, 'walk_sfx_sig.wav'), os.path.join(HERE, 'walk_sfx_beds.wav'),
                 os.path.join(HERE, 'fx_logs', 'sfx', 'sfx_only.wav')]
    for p, x in zip(paths, (mix, sig_i, bed_i, both)):
        wavfile.write(p, SR, x)
    print('wrote', ', '.join(os.path.basename(p) for p in paths), '| %.4f s, peak %.5f | finale: %s' % (
        len(mix) / SR, stats['peak'] / 32767, 'title_frame %d' % finale['title_frame'] if finale else 'no finale.json, chime skipped'))
    print('overs: music dip inside windows %d samples (deepest %.2f dB); bed dip outside windows %d samples (min gain %.3f); samples cut by the final clip %d' % (
        stats['music_dip_samples'], stats['music_dip_db'], stats['bed_dip_samples'], stats['bed_dip_min'], stats['clipped_by_final_clip']))
    print('bed rms against music rms: footsteps %.1f dB, murmur %.1f dB' % (20 * np.log10(lv['foot_rms'] / lv['music_rms']), 20 * np.log10(lv['crowd_rms'] / lv['music_rms'])))
    for e in info:
        print('%-8s %-15s %-6s frame %4d onset %7d pan %+.3f peak %.3f (%.1f dB vs local %.3f)' % (
            e['shop'], e['name'], e['kind'], e['frame'], e['i0'], e['pan'], e['peak'], 20 * np.log10(e['peak'] / e['local_peak']), e['local_peak']))
    print('sha256', ' '.join(hashlib.sha256(open(p, 'rb').read()).hexdigest()[:16] for p in paths))
    if '--check' in sys.argv:
        import subprocess
        subprocess.run([sys.executable, os.path.join(HERE, 'fx_logs', 'sfx', 'check_sfx.py')] + (['--dir', outdir] if outdir else []), check=False)
