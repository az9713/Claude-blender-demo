# fx_dancers.py - four beat-locked dancers (run by build_neighborhood_walk_v2.py with that script's globals; WALK_FX=dancers).
# Cookie pair: warm (sway, hop on every beat, arms swing and clap overhead on beat 1 of 4).
# Arcade pair: stiff "pixel" style (robot arm poses held a half beat, quick hops, head nods).
# All motion is procedural keyframes on the global beat grid (BEAT0 + k * BEAT). Amplitudes scale with PUNCH (default 2.5).
# Window: view frame - 60 .. view frame + 120. Before and after, the dancer stands (a slow sway like idle()). They never leave the spot.
at(Matrix.Identity(4))                       # make sure new objects are placed in world space
_DK = min(PUNCH / 2.5, 1.4)                   # amplitude factor: 1.0 at the default PUNCH 2.5 (capped so nobody flails)
_DL = (0.0, 0.0, 1.2)                         # pivot of the head (neck)


def _d_ease(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def _d_lerp(a, b, u):
    return a + (b - a) * u


def _d_table(b, tab):
    """Smooth periodic interpolation of a table [(beat_in_cycle, value), ...] with period 4 beats; the first entry is at 0."""
    b = b % 4.0
    pts = tab + [(4.0, tab[0][1])]
    for (b0, v0), (b1, v1) in zip(pts, pts[1:]):
        if b0 <= b <= b1:
            return _d_lerp(v0, v1, _d_ease((b - b0) / (b1 - b0)))
    return tab[0][1]


# ---- arm poses: (theta, phi). theta = swing about local Y (negative = forward and up), phi = roll about local X (sideways).
# arms[0] is on local +Y, arms[1] on local -Y; phi has the opposite sign on arms[1].
_A = 0.9 * _DK            # swing amplitude (rad, 52 degrees at PUNCH 2.5)
_CLAP = (-3.1, -0.52)     # both arms overhead, hands meet
_UP = (-2.9, 0.15)        # overhead, hands apart
_ARM_TAB = {              # cookie arms: one 4-beat cycle, arm 0 and arm 1 (swing in opposite directions)
    0: [(0.0, _CLAP), (0.5, _UP), (1.0, (-_A, 0.1)), (2.0, (_A, 0.1)), (3.0, (-_A, 0.1)), (3.5, (-1.9, 0.0))],
    1: [(0.0, _CLAP), (0.5, _UP), (1.0, (_A, 0.1)), (2.0, (-_A, 0.1)), (3.0, (_A, 0.1)), (3.5, (-1.9, 0.0))],
}


def _d_arm_smooth(b, i, swap):
    """(theta, phi) for arm i (phi already signed for that arm). swap = 1 mirrors the swing phase of the dancer."""
    tab = _ARM_TAB[(i + swap) % 2]
    th = _d_table(b, [(t_, v_[0]) for t_, v_ in tab])
    ph = _d_table(b, [(t_, v_[1]) for t_, v_ in tab])
    return th, ph * (1 if i == 0 else -1)


_P_REST, _P_FWD, _P_SIDE, _P_UP = (0.0, 0.0), (-1.57, 0.0), (0.0, 1.57), (-3.1, 0.12)
_P_DIAG, _P_FWDUP = (0.0, 2.4), (-2.35, 0.0)
_ROBOT = {   # 8 half-beat slots per 4 beats. Dancer 0: both arms mirror each other. Dancer 1: the arms alternate.
    0: ([_P_SIDE, _P_DIAG, _P_SIDE, _P_REST, _P_FWD, _P_FWDUP, _P_FWD, _P_REST],) * 2,
    1: ([_P_FWD, _P_REST, _P_FWD, _P_UP, _P_SIDE, _P_REST, _P_DIAG, _P_REST],
        [_P_SIDE, _P_REST, _P_DIAG, _P_REST, _P_FWD, _P_REST, _P_FWD, _P_UP]),
}


def _d_idle(f, ph):
    """Standing pose, same sway as idle(): slow sway every two beats (z kept >= 0)."""
    s = math.sin((f - BEAT0) / (2 * BEAT) * TAU + ph)
    return 0.015 * PUNCH * (1 + s) / 2, 0.12 * PUNCH * s


def _d_pose(f, style, k, env, ph):
    """All channel values at frame f. style 'warm' or 'robot'; k = 0 or 1 (which dancer of the pair)."""
    t = (f - BEAT0) / BEAT                      # time in beats from the grid origin
    iz, iarm = _d_idle(f, ph)
    P = dict(dx=0.0, z=iz, twist=0.0, legs=[0.0, 0.0], arm=[(iarm, 0.0), (0.0, 0.0)], neck=(0.0, 0.0, 0.0))   # neck = (roll x, pitch y, yaw z)
    if env <= 0.0:
        return P
    sgn = 1 if k == 0 else -1
    if style == 'warm':
        fr = t - math.floor(t)
        hop = 0.04 * PUNCH * math.sin(math.pi * fr)                       # lands on every beat, peak between beats
        sway = math.sin(math.pi * t + (0 if k == 0 else math.pi))        # mirrored: the pair sways towards and away from each other
        d = dict(dx=0.12 * sway, z=hop,
                 twist=0.14 * PUNCH * sway,
                 legs=[0.4 * math.sin(math.pi * t + i * math.pi + k) for i in (0, 1)],
                 arm=[_d_arm_smooth(t, i, k) for i in (0, 1)],
                 neck=(0.15 * sway, 0.12 * math.cos(TAU * t), 0.0))
    else:
        n2 = math.floor(t * 2 + 1e-9)             # half-beat slot (the value is held for the slot, snaps in one key step)
        n1 = math.floor(t + 1e-9)                 # beat slot
        fr = t - n1
        s8 = n2 % 8
        arms = []
        for i in (0, 1):
            th, ph_ = _ROBOT[k][i][s8]
            arms.append((th, ph_ * (1 if i == 0 else -1)))
        tw = 0.14 * PUNCH * [0, 1, 0, -1][n1 % 4] * sgn
        if k == 0:                                 # hops on the beat, nods on the beat
            hop_fr = fr
            nod = 0.4 if n2 % 2 == 0 else 0.0
            yaw = 0.0
        else:                                      # hops on the off beat, nods on the off beat and looks left and right
            hop_fr = (fr + 0.5) % 1.0
            nod = 0.4 if n2 % 2 == 1 else 0.0
            yaw = 0.5 * (1 if n1 % 2 == 0 else -1)
        hop = 0.035 * PUNCH * max(0.0, 1 - abs(4 * hop_fr - 1)) if hop_fr < 0.5 else 0.0
        lg = 0.35 * (1 if (n1 + k) % 2 == 0 else -1)
        d = dict(dx=0.0, z=hop, twist=tw, legs=[lg, -lg], arm=arms, neck=(0.0, nod, yaw))
    P['dx'] = d['dx'] * env
    P['z'] = _d_lerp(iz, d['z'] + 0.0, env)
    P['twist'] = d['twist'] * env
    P['legs'] = [d['legs'][0] * env, d['legs'][1] * env]
    P['arm'] = [(_d_lerp(P['arm'][i][0], d['arm'][i][0], env), d['arm'][i][1] * env) for i in (0, 1)]
    P['neck'] = tuple(v * env for v in d['neck'])
    return P


def _d_dancer(name, pos, psi, style, k, w0, w1, **look):
    p = person(name, **look)
    root = p['root']
    # head parts hang on a neck empty so the head can nod and turn on its own
    neck = empty(name + "_neck", _DL)
    neck.parent = root
    for o in [o for o in bpy.data.objects if o.parent is root and o.name.startswith(name + "_") and o is not neck]:
        o.parent = neck
        o.matrix_parent_inverse = Matrix.Translation((-_DL[0], -_DL[1], -_DL[2]))
    root.location = (pos[0], pos[1], 0.0)
    root.rotation_euler = (0.0, 0.0, psi)
    ph = 1.7 * k
    fine = BEAT / (8 if style == 'robot' else 4)
    kind = 'LINEAR' if style == 'robot' else 'BEZIER'
    times = {round(BEAT0 + j * BEAT / 2, 4) for j in range(int((-10 - BEAT0) // (BEAT / 2)), int((FRAMES + 12 - BEAT0) // (BEAT / 2)) + 1)}
    times = {t_ for t_ in times if t_ < w0 or t_ > w1}
    j0 = math.ceil((w0 - BEAT0) / fine - 1e-9)
    j1 = math.floor((w1 - BEAT0) / fine + 1e-9)
    times |= {round(BEAT0 + j * fine, 4) for j in range(j0, j1 + 1)} | {float(w0), float(w1)}
    for f in sorted(times):
        env = 0.0
        if w0 <= f <= w1:
            env = min(_d_ease((f - w0) / BEAT), _d_ease((w1 - f) / BEAT))     # one beat in, one beat out
        P = _d_pose(f, style, k, env, ph)
        kf(root, 'location', 0, f, pos[0] + P['dx'], kind)
        kf(root, 'location', 2, f, P['z'], kind)
        kf(root, 'rotation_euler', 2, f, psi + P['twist'], kind)
        for i in (0, 1):
            kf(p['legs'][i], 'rotation_euler', 1, f, P['legs'][i], kind)
            kf(p['arms'][i], 'rotation_euler', 1, f, P['arm'][i][0], kind)
            kf(p['arms'][i], 'rotation_euler', 0, f, P['arm'][i][1], kind)
        for ax in (0, 1, 2):
            kf(neck, 'rotation_euler', ax, f, P['neck'][ax], kind)
    return p


def _d_group(shop_kind, specs):
    si = next(i for i, S in enumerate(SHOP_LIST) if S['kind'] == shop_kind)
    w0, w1 = VIEW_T[si] - 60, VIEW_T[si] + 120
    for sp in specs:
        _d_dancer(w0=w0, w1=w1, **sp)
    _d_dodge([sp['pos'] for sp in specs], w0, w1)


def _d_fcurves(o):
    ad = o.animation_data
    if hasattr(ad.action, 'fcurves'):
        return list(ad.action.fcurves)
    from bpy_extras import anim_utils            # Blender 4.4+ layered actions
    return list(anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot).fcurves)


def _d_dodge(spots, w0, w1, R=1.0, K=10):
    """The base street traffic is keyed without knowing about the dancers. A walker whose keyed path comes closer than R (m) to a dancer
    spot during the dance window steps aside: a per-frame sideways displacement (zero outside the conflict, ramped over K frames each side)."""
    for m in bpy.data.objects:
        if m.type != 'EMPTY' or m.parent is not None or m.name.startswith('dance_') or not m.animation_data or not m.animation_data.action:
            continue
        if not any(c.name.startswith('torso') for c in m.children):      # persons only (not the cyclist or the car)
            continue
        fc = {f_.array_index: f_ for f_ in _d_fcurves(m) if f_.data_path == 'location' and f_.array_index in (0, 1)}
        if len(fc) < 2:
            continue
        dv = {}
        for f in range(w0 - K, w1 + K + 1):
            x0, y0 = fc[0].evaluate(f), fc[1].evaluate(f)
            x, y = x0, y0
            for _ in range(8):                   # relax: move away from every spot that is closer than R (a walker between two dancers ends in the middle)
                for (sx, sy) in spots:
                    d = math.hypot(x - sx, y - sy)
                    if d < R:
                        ux, uy = ((x - sx) / d, (y - sy) / d) if d > 0.02 else (0.0, -1.0 if sy < -9 else 1.0)    # away from the dancer; at zero distance towards the street
                        x, y = x + ux * (R - d), y + uy * (R - d)
            if abs(x - x0) + abs(y - y0) > 1e-6:
                dv[f] = (x - x0, y - y0)
        if not dv:
            continue
        lo, hi = min(dv) - K, max(dv) + K
        base = {f: (fc[0].evaluate(f), fc[1].evaluate(f)) for f in range(lo, hi + 1)}      # read the keyed path before inserting keys
        for f in range(lo, hi + 1):
            if f in dv:
                d = dv[f]
            else:                                # ramp down over K frames from the nearest conflict frame
                g = min(dv, key=lambda g_: abs(g_ - f))
                w = max(0.0, 1.0 - abs(g - f) / (K + 1.0))
                d = (dv[g][0] * w, dv[g][1] * w)
            kf(m, 'location', 0, f, base[f][0] + d[0], 'LINEAR')
            kf(m, 'location', 1, f, base[f][1] + d[1], 'LINEAR')


# Cookie pair stands on the north curb strip (y = -4.9), in front of the pedestrian lane (y -3.4..-4.1), so passers-by walk BEHIND them as seen from the camera.
# It faces the street (-Y), turned a little towards the camera side. The two are 5.5 m apart because the camera sees the curb at a shallow angle (13 degrees);
# a closer pair would hide one dancer behind the other. The name tag (screen x 350..700) stays clear.
# Positions come from a line-of-sight grid search (fx_logs/dancers2/search.py): all body points visible at view-20..view+20, >= 0.8 m from static props and
# from every other person at view-30..view+30.
_d_group('cookie', [
    dict(name="dance_cookie_a", pos=(-2.5, -4.9), psi=math.radians(-110), style='warm', k=0,
         shirt='#FFD166', pants='#5C4E7A', skin='#C98E62', hair='#4B2E24', dress='#FF9E6B'),
    dict(name="dance_cookie_b", pos=(3.0, -4.9), psi=math.radians(-110), style='warm', k=1,
         shirt='#4FC9BE', pants='#3D5A6C', skin='#F2C6A0', hair='#C98A4B', hat='#FF7FA8'),
])
# Arcade pair stands on the south sidewalk in front of the door (x 20.0 and 21.7, y -15.3) and faces the street (+Y). No passer-by comes within
# 0.8 m at view-30..view+30 (same grid search); 1.7 m apart so the robot arms do not reach the other dancer.
_d_group('arcade', [
    dict(name="dance_arcade_a", pos=(20.0, -15.25), psi=math.radians(105), style='robot', k=0,
         shirt='#7FB5FF', pants='#2F4B5C', skin='#8D5B3A', hair='#1F1B1A', hat='#E63946'),
    dict(name="dance_arcade_b", pos=(21.7, -15.3), psi=math.radians(105), style='robot', k=1,
         shirt='#C8B6F2', pants='#7A5C4E', skin='#F6D5B8', hair='#FF7FA8'),
])
