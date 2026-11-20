# fx_notes.py - drifting eighth notes that float up from the door of the shop whose tune plays.
# Run by build_neighborhood_walk_v2.py through the WALK_FX hook (uses its globals). One bar = 100 frames per shop.
# Each note = 3 low-poly parts (ico head with cream rim, box stem, wedge flag) under one empty with keyframes:
# location (rise + sideways drift + sway), roll (sway), scale 0 -> 1 -> 0. All notes are built once; a note has scale 0 outside its life.
# Batch 2 (notes2): colour = a deep shade of the shop's own palette (one flat tone for head, stem, flag, so the note is
# not heavier than its head), size per shop, and a fixed table of release slots / start positions chosen offline so that in
# view-20..view+20 no note covers a head, the door, the sign text, the name tag or the emblem (fx_logs/notes2/search.py).
_CREAM_N = M('#FFF6E6', 0.6, emit='#FFF6E6', strength=0.4)
NS = 1.6        # default note size factor: 0.4 m shape x 1.6 = 0.64 m (maximum allowed)
_BAR_ORDER = ['toy', 'book', 'ice', 'candy', 'cookie', 'pet', 'comic', 'train', 'bike', 'arcade']
_KIND_IDX = {S_['kind']: i_ for i_, S_ in enumerate(SHOP_LIST)}
_NSZ = {'book': 1.15}                                  # book: smaller (0.46 m); all others NS
_INK = {'toy': '#9B3833', 'book': '#A93744', 'ice': '#3F4EB8', 'candy': '#9F2E55',
        'cookie': '#6445A0', 'pet': '#7A4B2A', 'comic': '#9C1E4B', 'train': '#3D5A6C', 'bike': '#7F3919', 'arcade': '#7E123B'}
# per note: (release slot in beats after the bar start, life frames, start z, rise m, start x in the shop frame, drift m, sway phase, y in the shop frame)
_TABLE = {
    'toy': [(0, 76, 1.451, 1.514, 1.304, 0.310, 2.569, -1.871), (1, 60, 1.493, 1.528, 1.794, 0.400, 0.422, -2.294), (7, 80, 1.415, 1.601, -1.592, -0.307, 1.337, -2.287)],
    'book': [(2, 68, 1.469, 1.518, 0.752, 0.505, 1.207, -2.378), (3, 64, 1.504, 1.534, 1.478, 0.438, 0.170, -1.898), (5, 76, 1.521, 1.518, 0.787, 0.357, 2.773, -1.988), (7, 72, 1.467, 1.553, 1.331, -0.366, 1.628, -1.930)],
    'ice': [(0, 64, 1.484, 1.551, -3.281, -0.447, 3.938, -2.337), (0, 64, 1.515, 1.520, -2.470, -0.345, 3.646, -1.923), (7, 64, 1.524, 1.508, -1.329, 0.449, 5.931, -1.815), (7, 80, 1.529, 1.513, 1.302, 0.532, 4.838, -2.124)],
    'candy': [(0, 60, 1.443, 1.542, -0.709, 0.440, 5.397, -2.019), (1, 64, 1.409, 1.606, -0.596, 0.520, 2.863, -1.781), (3, 76, 1.431, 1.508, -0.486, 0.348, 6.077, -2.361), (5, 80, 1.491, 1.543, 0.481, 0.379, 4.025, -2.211), (6, 60, 1.513, 1.524, -0.853, -0.482, 4.448, -1.992)],
    'cookie': [(0, 72, 1.444, 1.548, -1.343, -0.492, 3.704, -2.367), (1, 64, 1.437, 1.612, -1.358, -0.539, 2.943, -2.312), (7, 68, 1.494, 1.534, 1.347, 0.324, 3.105, -1.777)],
    'pet': [(0, 64, 1.525, 1.507, -4.165, 0.342, 0.593, -2.083), (3, 80, 1.412, 1.612, -4.244, 0.365, 5.757, -1.843), (7, 72, 1.492, 1.552, -1.425, 0.304, 0.491, -2.206)],
    'comic': [(1, 64, 1.493, 1.546, 1.331, 0.423, 3.290, -1.780), (3, 64, 1.531, 1.517, 1.444, 0.461, 5.796, -1.824), (6, 80, 1.475, 1.570, 1.420, -0.522, 3.979, -2.031), (7, 76, 1.542, 1.507, 1.448, -0.484, 5.726, -2.340), (7, 76, 1.425, 1.517, 4.121, -0.363, 5.087, -2.185)],
    'train': [(0, 76, 1.482, 1.531, 4.183, -0.538, 1.672, -2.269), (1, 72, 1.444, 1.592, 4.304, -0.433, 0.256, -1.910), (5, 80, 1.431, 1.570, 4.196, -0.482, 2.677, -2.250), (7, 76, 1.528, 1.520, 4.165, -0.479, 4.572, -2.267)],
    'bike': [(0, 72, 1.484, 1.559, -0.002, -0.436, 4.720, -1.770), (1, 80, 1.464, 1.507, -0.968, 0.373, 4.433, -1.884), (2, 64, 1.507, 1.518, -1.318, -0.468, 0.115, -1.973), (4, 60, 1.549, 1.501, -1.195, -0.335, 0.353, -1.813)],
    'arcade': [(0, 64, 1.484, 1.541, -1.459, 0.329, 4.571, -1.769), (0, 72, 1.514, 1.505, -1.981, -0.506, 1.368, -2.122), (6, 60, 1.509, 1.532, 2.186, 0.343, 0.721, -2.062), (7, 72, 1.483, 1.501, -1.324, -0.546, 0.153, -1.906)],
}
NOTE_RIGS = []                      # (rig, bar number, release frame, life) - read by the test probes


def _smooth(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def _make_note(S, tag, ink):
    """One note, 0.4 m tall, centred on the origin, flat in the XZ plane (readable from both sides)."""
    mcore = M(shade(ink, 0.35), 0.8, emit=ink, strength=_EMS)
    parts = [
        ico("note_rim", (0, 0, -0.13), (0.135, 0.035, 0.105), _CREAM_N, sub=1, shadow=False),
        box("note_stem_rim", 0.05, 0.12, -0.012, 0.012, -0.14, 0.212, _CREAM_N, shadow=False),                  # cream outline of stem and flag (batch 2)
        tri_prism("note_flag_rim", [(0.09, 0.214), (0.235, 0.055), (0.09, 0.075)], 0.024, _CREAM_N, y0=-0.012, shadow=False),
        ico("note_head", (0, 0, -0.13), (0.095, 0.07, 0.068), mcore, sub=1, shadow=False),
        box("note_stem", 0.065, 0.105, -0.02, 0.02, -0.13, 0.2, mcore, shadow=False),
        tri_prism("note_flag", [(0.105, 0.2), (0.215, 0.07), (0.105, 0.09)], 0.04, mcore, y0=-0.02, shadow=False),
    ]
    rig = empty("note_" + tag)
    adopt(parts, rig)
    return rig


_EMS = 0.8
at(Matrix.Identity(4))
for _bar, _kind in enumerate(_BAR_ORDER, start=1):
    _si = _KIND_IDX[_kind]
    _S = SHOP_LIST[_si]
    _start = VIEW_T[_si] - 50
    _ns = _NSZ.get(_kind, NS)
    for _ni, (_b, _life, _z0, _rise, _lx, _drift, _ph, _ly) in enumerate(_TABLE[_kind]):
        _rel = _start + _b * BEAT                          # on the beat grid: bar start is a multiple of BEAT from BEAT0
        # _ly is -1.75 to -2.4: street side of the awning edge (y=-1.3) and bulbs (y=-1.38)
        _rig = _make_note(_S, "%s_%d" % (_kind, _ni), _INK[_kind])
        NOTE_RIGS.append((_rig, _bar, _rel, _life))
        _step = BEAT / 4
        for _f_rel in [_j * _step for _j in range(int(_life / _step) + 1)] + [_life]:   # keys every quarter beat, plus one exactly at the end of life
            _t = _f_rel / _life
            _f = _rel + _f_rel
            _e = _smooth(_t)
            _lxx = _lx + _drift * _e + 0.15 * math.sin(_t * 2.2 * TAU + _ph) * min(1.0, 3 * _t)   # sideways drift <= 0.7 m
            _lz = _z0 + _rise * (0.6 * _t + 0.4 * _e)
            _w = shop_matrix(_S['cx'], _S['side']) @ Vector((_lxx, _ly, _lz))
            _sc = _smooth(_t / 0.18) * _smooth((1 - _t) / 0.3)                                 # grows in, shrinks out
            _sc *= 1 + 0.03 * PUNCH * math.cos((_f - BEAT0) / BEAT * TAU)                       # tiny pulse on the beat
            _sc = 0.001 if _t <= 0.0 or _t >= 1.0 else max(_sc, 0.001)
            kf(_rig, 'location', None, _f, (_w.x, _w.y, _w.z), 'LINEAR')
            _cx = CAM_X[max(0, min(len(CAM_X) - 1, int(_f) - 1))]
            _dx, _dy = _cx - _w.x, Y_MID - _w.y
            _yaw = math.atan2(-_dx, _dy) if _dy > 0 else math.atan2(_dx, -_dy)    # the flat face turns to the walker (the note is the same on both faces)
            kf(_rig, 'rotation_euler', None, _f, (0.0, 0.22 * math.sin(_t * 1.6 * TAU + _ph), _yaw), 'LINEAR')
            _sc *= _ns
            kf(_rig, 'scale', None, _f, (_sc, _sc, _sc), 'LINEAR')
        # before the note starts the first key (scale 0.001) holds; after the last key the scale stays 0.001
print("FX notes: %d notes" % len(NOTE_RIGS))
