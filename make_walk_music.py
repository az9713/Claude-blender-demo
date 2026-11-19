"""Lofi background music for Walk.mp4, synthesised with numpy (no samples, no AI model).
Every shop gets exactly one bar (100 video frames = 4.167 s) that starts 50 frames before the camera looks at it.
Each bar has its own chord, lead instrument, melody and drum feel. Run: python make_walk_music.py  -> walk_music.wav
Time map (24 fps, 1441 frames = 60.04 s): bar k starts at 2.917 + 4.167 k s. Bars 1..10 = toy, book, ice cream, candy, cookie,
pet, comic, train, bike, arcade (the order the camera looks at them). Bar 0 = intro, bars 11-12 = outro, then the last chord rings."""
import numpy as np, wave, os
from scipy.signal import lfilter, butter, sosfilt, fftconvolve

SR = 44100
T = 1441 / 24
B = 100 / 24            # one bar = 16 steps
E = B / 16              # one step (an eighth note at about 115 bpm; the snare plays half-time, so it feels slow)
B0 = B * 0.7            # bar 0 starts here (2.917 s); the first bar of a shop is at 7.083 s
rng = np.random.default_rng(5)
mid = lambda m: 440.0 * 2 ** ((m - 69) / 12)
tt = lambda d: np.arange(int(d * SR)) / SR


def rel(t, d, r=0.3):
    return np.clip(1 - (t - d) / r, 0, 1)


# ------------------------------------------------------------- instruments (each returns a mono array)
def rhodes(f, d, v=1.0):
    t = tt(d + 0.5)
    s = np.sin(2 * np.pi * f * t + (1.1 * np.exp(-t / 0.25) + 0.2) * np.sin(2 * np.pi * f * t))
    s += 0.12 * np.sin(2 * np.pi * f * 7 * t) * np.exp(-t / 0.03)
    return v * s * np.exp(-t / 1.5) * np.clip(t / 0.006, 0, 1) * rel(t, d, 0.4)


def bell(f, d, v=1.0, tau=1.3, parts=((1, 1, 1), (2.76, .45, .55), (5.4, .25, .3), (8.9, .12, .15))):
    t = tt(d + 0.5)
    s = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / (tau * k)) for r, a, k in parts)
    return v * s * np.clip(t / 0.002, 0, 1) * rel(t, d + 1.2, 0.6) * 0.5


def vibes(f, d, v=1.0):
    t = tt(d + 0.6)
    s = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 4 * t) * np.exp(-t / 0.2)) * np.exp(-t / 1.1)
    return v * s * (1 + 0.25 * np.sin(2 * np.pi * 5 * t)) * np.clip(t / 0.003, 0, 1) * rel(t, d + 0.5, 0.5) * 0.8


def flute(f, d, v=1.0):
    t = tt(d + 0.3)
    ph = 2 * np.pi * np.cumsum(f * (1 + 0.004 * np.sin(2 * np.pi * 5.2 * t) * np.clip(t / 0.4, 0, 1))) / SR
    env = np.clip(t / 0.09, 0, 1) * rel(t, d, 0.25)
    breath = lfilter(*butter(2, 2500 / (SR / 2)), rng.normal(0, 1, len(t))) * 0.05
    return v * (np.sin(ph) + 0.22 * np.sin(2 * ph) + 0.05 * np.sin(3 * ph) + breath) * env


def pluck(f, d, v=1.0, g=0.997):
    n0 = int(SR / f)
    n = int((d + 0.5) * SR)
    x = np.zeros(n)
    x[:n0] = lfilter([1, 1], [1], rng.uniform(-1, 1, n0)) * 0.5
    a = np.zeros(n0 + 2)
    a[0], a[n0], a[n0 + 1] = 1, -g / 2, -g / 2
    y = lfilter([1], a, x)
    return v * y * rel(np.arange(n) / SR, d, 0.35)


def chip(f, d, v=1.0, duty=0.25):
    t = tt(d + 0.05)
    s = np.where((t * f) % 1 < duty, 1.0, -1.0)
    s = np.round(s * 7) / 7
    return v * 0.5 * s * np.clip(t / 0.002, 0, 1) * np.exp(-t / 0.14) * rel(t, d, 0.04)


def bass(f, d, v=1.0):
    t = tt(d + 0.2)
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t)
    return v * s * np.clip(t / 0.012, 0, 1) * np.exp(-t / 1.0) * rel(t, d, 0.12)


def pad(notes, d, v=1.0):
    t = tt(d + 1.2)
    s = sum(np.sin(2 * np.pi * mid(m) * t) + 0.25 * np.sin(2 * np.pi * mid(m) * 2.003 * t) for m in notes) / len(notes)
    return v * s * np.clip(t / 0.7, 0, 1) * rel(t, d, 1.2) * (1 + 0.12 * np.sin(2 * np.pi * 0.35 * t))


def kick(v=1.0):
    t = tt(0.3)
    return v * np.sin(2 * np.pi * np.cumsum(45 + 80 * np.exp(-t / 0.035)) / SR) * np.exp(-t / 0.11)


def snare(v=1.0):
    t = tt(0.25)
    n = lfilter(*butter(2, [1200 / (SR / 2), 6000 / (SR / 2)], 'band'), rng.normal(0, 1, len(t)))
    return v * (0.6 * n * np.exp(-t / 0.07) + 0.4 * np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.05))


def hat(v=1.0, open_=False):
    t = tt(0.12 if open_ else 0.045)
    n = lfilter(*butter(2, 7000 / (SR / 2), 'high'), rng.normal(0, 1, len(t)))
    return v * n * np.exp(-t / (0.05 if open_ else 0.012))


def chug(v=1.0):   # brush / steam: filtered noise swell
    t = tt(0.16)
    n = lfilter(*butter(2, [900 / (SR / 2), 4500 / (SR / 2)], 'band'), rng.normal(0, 1, len(t)))
    return v * n * np.clip(t / 0.02, 0, 1) * np.exp(-t / 0.05)


def click(v=1.0):
    t = tt(0.012)
    return v * rng.normal(0, 1, len(t)) * np.exp(-t / 0.002)


def whistle(f0, f1, d, v=1.0):
    t = tt(d)
    f = np.linspace(f0, f1, len(t)) * (1 + 0.01 * np.sin(2 * np.pi * 6 * t))
    return v * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.clip(t / 0.03, 0, 1) * rel(t, d - 0.05, 0.05)


# ------------------------------------------------------------- harmony: name -> (bass note, voicing)
CH = {'Cmaj9': (36, [52, 55, 59, 62]), 'Am9': (45, [55, 59, 60, 64]), 'Fmaj9': (41, [52, 55, 57, 60]), 'G69': (43, [59, 62, 64, 69]),
      'Dm9': (38, [53, 57, 60, 64]), 'Bbmaj7#11': (46, [62, 65, 69, 64]), 'Em7': (40, [55, 59, 62, 64]), 'A7': (45, [55, 61, 64, 69]),
      'Dm7': (38, [53, 57, 60, 62]), 'G9': (43, [53, 57, 59, 62]), 'Am7': (45, [55, 60, 64, 67]), 'D9': (38, [54, 57, 60, 64])}
ALL = [i * 0.5 for i in range(32)]
EIGHTH = [float(i) for i in range(16)]
COMP = [(0, 5), (6.5, 2), (8, 4), (11.5, 3)]
BASS = [(0, 5), (6.5, 1.5), (8, 5), (14, 1.5)]

# lead = (instrument, [(step, midi, length in steps)], gain, pan)   pan -1 left .. +1 right
BARS = [
    dict(n='intro', ch=['Cmaj9'], kick=[], snare=[], hat=[], comp=[(0, 9)], bass=[(0, 10)], dg=0.5,
         leads=[('bell', [(0, 76, 3)], 0.10, 0.2)]),
    dict(n='Toy Box: music box', ch=['Cmaj9'], kick=[0, 10], snare=[], hat=[2, 6, 10, 14], comp=COMP, bass=BASS, dg=0.8,
         leads=[('bell', [(0, 76, 2), (2, 79, 2), (4, 84, 3), (6, 79, 2), (8, 76, 2), (10, 74, 2), (12, 72, 4)], 0.27, -0.2)]),
    dict(n='Page Turner Books: flute, no drums', ch=['Am9'], kick=[], snare=[], hat=[], comp=[(0, 10)], bass=[(0, 12)], dg=0.0,
         leads=[('flute', [(0, 76, 6), (6, 74, 2), (8, 72, 4), (12, 71, 3.5)], 0.22, 0.1)]),
    dict(n='Scoops Ice Cream: vibes, swing', ch=['Fmaj9'], kick=[0, 7, 10], snare=[4, 12], hat=EIGHTH, comp=COMP, bass=BASS, dg=1.0,
         leads=[('vibes', [(0, 81, 1.5), (3, 79, 1), (4, 81, 1.5), (7, 84, 1), (8, 81, 1.5), (11, 79, 1), (12, 77, 2), (14, 76, 2)], 0.20, 0.2)]),
    dict(n='Sweet Tooth Candy: glockenspiel sprinkles', ch=['G69'], kick=[0, 8], snare=[4, 12], hat=ALL, comp=COMP, bass=BASS, dg=1.0,
         leads=[('glock', [(0, 83, 1), (1, 86, 1), (2, 88, 1), (3, 91, 1), (6, 88, 1), (7, 86, 1), (8, 83, 1), (10, 81, 1), (12, 79, 1),
                           (13, 86, .7), (14, 83, .7), (15, 79, .7)], 0.16, -0.3)]),
    dict(n='Kevin Cookie Company: the warm theme', ch=['Fmaj9', 'Cmaj9'], kick=[0, 7, 10], snare=[4, 12], hat=EIGHTH, comp=COMP, bass=BASS, dg=1.0, pad=1.6,
         leads=[('rhodes', [(0, 84, 3), (3, 81, 1), (4, 79, 2), (6, 77, 2), (8, 76, 2), (10, 79, 2), (12, 83, 2), (14, 84, 2)], 0.26, 0.0),
                ('bell', [(8, 91, 1), (12, 95, 1), (14, 96, 1)], 0.07, 0.3)]),
    dict(n='Puppy Pals: plucked ukulele trot', ch=['Dm9'], kick=[0, 6, 8], snare=[4, 12], hat=[2, 6, 10, 14], comp=COMP, bass=BASS, dg=1.0,
         leads=[('pluck', [(0, 74, 1), (2, 77, 1), (3, 81, 1), (6, 77, 1), (8, 76, 1), (10, 74, 1), (11, 72, 1), (14, 69, 1)], 0.30, -0.2)]),
    dict(n='Pixel Comics: chip pulse', ch=['Bbmaj7#11'], kick=[0, 3, 8, 11], snare=[4, 12], hat=EIGHTH, comp=COMP, bass=BASS, dg=1.0,
         leads=[('chip', [(0, 70, .5), (2, 74, .5), (4, 77, .5), (6, 81, .5), (7, 76, .5), (8, 74, .5), (10, 77, .5), (12, 70, .5), (14, 76, .5)], 0.14, 0.3)]),
    dict(n='Choo Choo Hobbies: train chug and whistle', ch=['Em7', 'A7'], kick=[0, 4, 8, 12], snare=[], hat=[], chug=[0, 2, 3, 4, 6, 7, 8, 10, 11, 12, 14, 15],
         comp=[(0, 2), (2, 1), (4, 2), (8, 2), (10, 1), (12, 2)], bass=[(0, 3), (4, 3), (8, 3), (12, 3)], dg=0.9,
         leads=[('rhodes', [(0, 76, 2), (2, 74, 2), (4, 71, 3), (8, 73, 2), (10, 76, 2), (12, 81, 2), (14, 79, 2)], 0.22, 0.1)],
         whistles=[(12.5, 659, 659, 0.35), (13.9, 659, 784, 0.6)]),
    dict(n='Spoke & Roll: guitar picking and wheel ticks', ch=['Dm7', 'G9'], kick=[0, 5, 8, 13], snare=[4, 12], hat=ALL, comp=COMP, bass=BASS, dg=1.0,
         leads=[('pluck', [(i, m, 2) for i, m in enumerate([62, 65, 69, 72, 69, 65, 69, 72, 67, 71, 74, 77, 74, 71, 74, 77])], 0.30, 0.2)], ticks=True),
    dict(n='Arcade Alley: 8-bit arpeggio and coin', ch=['Am7', 'D9'], kick=[0, 4, 8, 12], snare=[4, 12], hat=ALL, comp=COMP, bass=BASS, dg=1.0,
         leads=[('chip', [(i * 0.5, m, .5) for i, m in enumerate([69, 72, 76, 81, 76, 72, 76, 81])] +
                         [(8 + i * 0.5, m, .5) for i, m in enumerate([66, 69, 72, 76, 72, 69, 72, 76])] + [(14, 83, .5), (14.5, 88, 1.2)], 0.12, -0.3)]),
    dict(n='outro 1: the theme again', ch=['Fmaj9', 'Cmaj9'], kick=[0, 10], snare=[4, 12], hat=[2, 6, 10, 14], comp=COMP, bass=BASS, dg=0.7,
         leads=[('rhodes', [(0, 84, 3), (3, 81, 1), (4, 79, 2), (6, 77, 2), (8, 76, 2), (10, 79, 2), (12, 84, 4)], 0.20, 0.0)]),
    dict(n='outro 2: last chord', ch=['Cmaj9'], kick=[], snare=[], hat=[], comp=[(0, 14)], bass=[(0, 14)], dg=0.0, pad=1.4,
         leads=[('rhodes', [(0, 84, 10)], 0.16, 0.0), ('bell', [(4, 96, 2)], 0.05, 0.3)]),
]
INST = {'bell': bell, 'glock': lambda f, d, v: bell(f, d, v, tau=0.6, parts=((1, 1, 1), (3.0, .35, .5), (6.2, .2, .3))),
        'vibes': vibes, 'flute': flute, 'rhodes': rhodes, 'pluck': pluck, 'chip': chip}

L = np.zeros(int(SR * (T + 1)))
R = np.zeros_like(L)
SEND = np.zeros_like(L)


def put(sig, t0, pan=0.0, gain=1.0, send=0.0):
    i0 = int(t0 * SR)
    if i0 < 0 or i0 >= len(L):
        return
    n = min(len(sig), len(L) - i0)
    s = sig[:n] * gain
    L[i0:i0 + n] += s * np.cos((pan + 1) * np.pi / 4)
    R[i0:i0 + n] += s * np.sin((pan + 1) * np.pi / 4)
    SEND[i0:i0 + n] += s * send


def when(k, step, jit=0.006):
    sw = 0.14 if (step % 2) == 1 else 0.0   # swing: odd steps land late
    return B0 + k * B + (step + sw) * E + rng.normal(0, jit)


def chord_at(bar, step):
    return CH[bar['ch'][0 if (step < 8 or len(bar['ch']) == 1) else -1]]


for k, bar in enumerate(BARS):
    dg = bar['dg']
    # pad: one swell per chord
    for h, name in enumerate(bar['ch']):
        span = B if len(bar['ch']) == 1 else B / 2
        put(pad(CH[name][1] + [CH[name][0] + 12], span + 0.2, 1.0), B0 + k * B + h * span, 0.0, 0.05 * bar.get('pad', 1.0), 0.5)
    if k == 0:   # intro swell before the first bar
        put(pad(CH['Cmaj9'][1], 2.8, 1.0), 0.0, 0.0, 0.03, 0.5)
    for (st, ln) in bar['comp']:
        _, v = chord_at(bar, st)
        for j, m in enumerate(v):
            put(rhodes(mid(m), ln * E, 0.55 * rng.uniform(0.85, 1.1)), when(k, st + j * 0.04), (j - 1.5) * 0.12, 0.09, 0.35)
    for (st, ln) in bar['bass']:
        put(bass(mid(chord_at(bar, st)[0]), ln * E, 1.0), when(k, st, 0.003), 0.0, 0.26)
    for st in bar['kick']:
        put(kick(1.0), when(k, st, 0.003), 0.0, 0.55 * dg)
    for st in bar['snare']:
        put(snare(1.0), when(k, st, 0.004), 0.1, 0.20 * dg, 0.3)
    for st in bar['hat']:
        put(hat(1.0, open_=(st == 14)), when(k, st), 0.25, (0.05 if st % 2 else 0.035) * max(dg, 0.5) * rng.uniform(0.7, 1.2))
    for st in bar.get('chug', []):
        put(chug(1.0), when(k, st), -0.2, 0.06)
    if bar.get('ticks'):   # freewheel ticks, slowing down through the bar
        t = 0.0
        while t < B * 0.95:
            put(click(1.0), B0 + k * B + t, 0.3, 0.05)
            t += 0.05 + 0.14 * (t / B)
    for (st, f0, f1, d) in bar.get('whistles', []):
        put(whistle(f0, f1, d, 1.0), when(k, st, 0.0), 0.2, 0.05, 0.4)
    for (inst, notes, g, pan) in bar['leads']:
        for (st, m, ln) in notes:
            put(INST[inst](mid(m), ln * E, rng.uniform(0.9, 1.05)), when(k, st, 0.008), pan, g, 0.45)

# ------------------------------------------------------------- master: reverb, tape wobble, tone, crackle, fades
ir_t = tt(1.8)
for ch_, buf in (('L', L), ('R', R)):
    ir = rng.normal(0, 1, len(ir_t)) * np.exp(-ir_t / 0.45)
    ir = lfilter(*butter(1, 3200 / (SR / 2)), ir)
    ir[:int(0.012 * SR)] = 0
    ir /= np.sqrt((ir ** 2).sum())
    buf += 0.55 * fftconvolve(SEND, ir)[:len(buf)]
t = np.arange(len(L)) / SR
wob = 0.0007 * np.sin(2 * np.pi * 0.55 * t) + 0.0003 * np.sin(2 * np.pi * 3.3 * t + 1.0)
sos = np.vstack([butter(2, 6200 / (SR / 2), output='sos'), butter(2, 40 / (SR / 2), 'high', output='sos')])
out = []
for buf in (L, R):
    x = np.interp(t + wob, t, buf)
    x = sosfilt(sos, x)
    x = np.tanh(1.3 * x) / 1.3
    out.append(x)
crackle = np.zeros(len(t))
idx = rng.integers(0, len(t), int(T * 22))
crackle[idx] = rng.normal(0, 1, len(idx)) * rng.uniform(0.02, 0.12, len(idx))
crackle = lfilter(*butter(1, 9000 / (SR / 2), 'high'), crackle) + rng.normal(0, 0.0012, len(t))
fade = np.clip(t / 1.2, 0, 1) * np.clip((T - t) / 2.8, 0, 1)
y = np.stack([(out[0] + crackle) * fade, (out[1] + np.roll(crackle, 37)) * fade], axis=1)[:int(T * SR)]
y *= 0.89 / np.abs(y).max()
here = os.path.dirname(os.path.abspath(__file__))
with wave.open(os.path.join(here, 'walk_music.wav'), 'wb') as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((y * 32767).astype('<i2').tobytes())
print('wrote walk_music.wav', len(y) / SR, 's, peak', float(np.abs(y).max()))
