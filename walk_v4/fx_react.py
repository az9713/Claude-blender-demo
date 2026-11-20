# fx_react.py - people and the dog react to the camera as it walks past (run by build_neighborhood_walk_v2.py with that script's globals; WALK_FX=react).
# Seven reactions on people who already walk or stand near the camera line. Each one peaks on a beat frame (BEAT0 + k * BEAT) and lasts at most 40 frames:
#   383.5 enter_book_2 glances back and waves | 421 adultS1 raises the shopping bag and nods | 508.5 enter_candy_2 (kid) jumps twice (apexes 496 and 508.5) | 796 teenS follows the camera with the head and tips the cap
#   846 leave_comic_2 glances back and waves three times | 958.5 leave_train_0 throws both arms up (bag overhead) | 983.5 dog looks up at the camera, tail up and wagging.
# Rules kept: no location key of any person is touched; legs are never touched (the walk cycle and the footfalls stay). Only added or blended:
#   head (a neck empty, as in fx_dancers.py), arm rotation keys (the walk swing is blended out inside the window and back in), and for the jumping kid
#   one body empty named torso_hop_* (the name starts with "torso" so fx_dancers._d_dodge still sees the kid as a person).
# Amplitudes follow PUNCH a little (factor _RK = 1.0 at the default 2.5). All helper names start with _r_ so no other fx file is hit.
_r_cur = CUR                                        # new objects are made in world space; the old matrix comes back at the end
at(Matrix.Identity(4))
_RK = 0.7 + 0.3 * min(PUNCH / 2.5, 1.4)


def _r_fc(o):
    ad = o.animation_data
    if ad is None or ad.action is None:
        return {}
    if hasattr(ad.action, 'fcurves'):
        fcs = list(ad.action.fcurves)
    else:                                            # Blender 4.4+ layered actions
        from bpy_extras import anim_utils
        fcs = list(anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot).fcurves)
    return {(f_.data_path, f_.array_index): f_ for f_ in fcs}


_R_CAM = _r_fc(cam)


def _r_ease(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def _r_ramp(f, a, b):
    return _r_ease((f - a) / (b - a))


def _r_bump(f, c, w):
    return math.exp(-((f - c) / w) ** 2)


def _r_tab(f, tab):
    """Smooth interpolation of [(frame, v0, v1, ...), ...]; held before the first and after the last row."""
    if f <= tab[0][0]:
        return tab[0][1:]
    for a, b in zip(tab, tab[1:]):
        if a[0] <= f <= b[0]:
            u = _r_ease((f - a[0]) / (b[0] - a[0]))
            return tuple(x + (y - x) * u for x, y in zip(a[1:], b[1:]))
    return tab[-1][1:]


def _r_cam_xy(f):
    return _R_CAM[('location', 0)].evaluate(f), _R_CAM[('location', 1)].evaluate(f)


def _r_dir(root, f):
    """Angle (rad, -pi..pi) from the heading of `root` to the direction towards the camera at frame f (positive = camera on the left side)."""
    fc = _r_fc(root)
    x = fc[('location', 0)].evaluate(f) if ('location', 0) in fc else root.location.x
    y = fc[('location', 1)].evaluate(f) if ('location', 1) in fc else root.location.y
    h = fc[('rotation_euler', 2)].evaluate(f) if ('rotation_euler', 2) in fc else root.rotation_euler.z
    cx, cy = _r_cam_xy(f)
    return (math.atan2(cy - y, cx - x) - h + math.pi) % TAU - math.pi


def _r_write(o, path, idx, w0, w1, fn, extra=()):
    """Write channel (path, idx) of o over [w0, w1]. fn(f, base) -> value, base = the existing curve (or the property) at f. The old keys strictly inside the window
    are removed; keys at w0, w1, every whole frame and the frames in `extra` are written. fn must return base at w0 and w1 so the curve joins."""
    fc = _r_fc(o).get((path, idx))
    cur = getattr(o, path)[idx]
    base = (lambda f_: fc.evaluate(f_)) if fc else (lambda f_: cur)
    fr = sorted({float(k) for k in range(math.ceil(w0), math.floor(w1) + 1)} | {float(w0), float(w1)} | {float(e) for e in extra if w0 <= e <= w1})
    vals = [fn(f_, base(f_)) for f_ in fr]
    if fc:
        for kp in [k for k in fc.keyframe_points if w0 < k.co[0] < w1][::-1]:
            fc.keyframe_points.remove(kp)
    for f_, v_ in zip(fr, vals):
        kf(o, path, idx, f_, v_)


def _r_parts(root):
    ch = list(root.children)
    arms = sorted([c for c in ch if c.name.startswith('arm')], key=lambda a: -a.location.y)    # [0] on local +Y, [1] on local -Y
    if root.name == 'dog':
        head = [c for c in ch if c.name.startswith(('dog_head', 'dog_snout', 'dog_nose', 'dog_ear'))]
    else:
        head = [c for c in ch if c.name.startswith(root.name + '_')]
    return arms, head


def _r_neck(root, head, pivot):
    n = empty(root.name + "_rneck", pivot)
    n.parent = root
    n.location = pivot
    for o in head:
        o.parent = n
        o.matrix_parent_inverse = Matrix.Translation((-pivot[0], -pivot[1], -pivot[2]))
    return n


def _r_arm_pose(arm, side, w0, w1, env, th_t, ph_t, extra=()):
    """Blend arm `arm` from the walk swing to the pose (th_t(f), ph_t(f)) by env(f) (0..1). side = +1 for the arm on local +Y, -1 for -Y (roll sign)."""
    def th(f, b):
        e = 0.0 if f <= w0 or f >= w1 else env(f)
        return b + (th_t(f) - b) * e

    def ph(f, b):
        e = 0.0 if f <= w0 or f >= w1 else env(f)
        return b + (side * ph_t(f) - b) * e
    _r_write(arm, 'rotation_euler', 1, w0, w1, th, extra)
    _r_write(arm, 'rotation_euler', 0, w0, w1, ph, extra)


def _r_nod(neck, w0, w1, pitch=None, yaw=None, roll=None, scale=None, extra=()):
    for idx, fn in ((0, roll), (1, pitch), (2, yaw)):
        if fn is None:
            continue
        _r_write(neck, 'rotation_euler', idx, w0, w1, (lambda f, b, fn=fn: 0.0 if (f <= w0 or f >= w1) else fn(f)), extra)
    if scale is not None:
        for idx in (0, 1, 2):
            _r_write(neck, 'scale', idx, w0, w1, (lambda f, b, idx=idx: 1.0 if (f <= w0 or f >= w1) else scale(f)[idx]), extra)


def _r_bag(name, P):
    """Shopper nods and lifts the shopping bag towards the camera. Bag arm: forward and up 92 degrees (106 at the accent on beat P); head nod 29 degrees on the beat."""
    root = bpy.data.objects[name]
    arms, head = _r_parts(root)
    bagarm = next(a for a in arms if any(c.name.startswith('bag') for c in a.children))
    side = 1 if bagarm is arms[0] else -1
    w0, w1 = P - BEAT, P + BEAT          # short: after P + BEAT the shopper walks into another person (base path) and is out of frame on the right
    env = lambda f: _r_ramp(f, P - BEAT, P) * (1 - _r_ramp(f, P + 0.3 * BEAT, w1))
    _r_arm_pose(bagarm, side, w0, w1, env, lambda f: -(1.6 + 0.25 * _r_bump(f, P, 4.5)) * _RK, lambda f: 0.0, extra=(P,))   # +14 degrees accent: the pose peaks at P
    neck = _r_neck(root, head, (0.0, 0.0, 1.2))
    nod = lambda f: _RK * 0.5 * _r_bump(f, P, 3.5)
    _r_nod(neck, w0, w1, pitch=nod, scale=lambda f: (1 + 0.05 * _r_bump(f, P, 3.5),) * 2 + (1 - 0.08 * _r_bump(f, P, 3.5),), extra=(P,))
    return (name, 'bag raise + nod', w0, P, w1, 'arm %.0f deg, head pitch %.0f deg' % (math.degrees(1.85 * _RK), math.degrees(0.5 * _RK)))


def _r_follow(name, P):
    """The head follows the camera (yaw = direction to the camera relative to the body heading, limit 72 degrees, plus a nod and a head tilt) and the hand nearest
    to the camera goes to the cap brim (tips the cap): arm forward and up 149 degrees, slightly inward."""
    root = bpy.data.objects[name]
    arms, head = _r_parts(root)
    w0, w1 = P - 14, P + 26
    env = lambda f: _r_ramp(f, P - 14, P - 3) * (1 - _r_ramp(f, P + 8, w1))
    lim = 1.25
    yaw = lambda f: env(f) * max(-lim, min(lim, _r_dir(root, f)))
    neck = _r_neck(root, head, (0.0, 0.0, 1.2))
    _r_nod(neck, w0, w1, pitch=lambda f: _RK * 0.3 * _r_bump(f, P, 4.0), yaw=yaw,
           roll=lambda f: 0.14 * _RK * env(f) * (1 if _r_dir(root, P) > 0 else -1),
           scale=lambda f: (1 + 0.04 * _r_bump(f, P, 4.0),) * 2 + (1 - 0.06 * _r_bump(f, P, 4.0),), extra=(P,))
    near = 0 if _r_dir(root, P) > 0 else 1
    _r_arm_pose(arms[near], 1 if near == 0 else -1, w0, w1, env, lambda f: -(2.6 + 0.2 * _r_bump(f, P, 4.5)) * _RK, lambda f: -0.35, extra=(P,))
    return (name, 'head follows camera + tips cap', w0, P, w1, 'head yaw %.0f deg (limit 72), arm %.0f deg' % (math.degrees(max(-lim, min(lim, _r_dir(root, P)))), math.degrees(2.8 * _RK)))


def _r_wave(name, P):
    """The shopper glances back at the camera (head yaw to the camera, limit 72 degrees) and waves with the free arm three times. The arm swings in the walking
    direction plane (the camera sees people from the side): mean 143 degrees forward and up, 63 degrees peak to peak; apexes (arm vertical) on the beats P - BEAT, P, P + BEAT."""
    root = bpy.data.objects[name]
    arms, head = _r_parts(root)
    free = [a for a in arms if not any(c.name.startswith('bag') for c in a.children)]
    arm = free[0] if len(free) == 1 else arms[0 if _r_dir(root, P) > 0 else 1]      # the free arm, or the arm nearest to the camera
    side = 1 if arm is arms[0] else -1
    w0, w1 = P - 1.48 * BEAT, P + 1.64 * BEAT         # raise 6 frames before the first swing, lower 8 frames after the third
    env = lambda f: _r_ramp(f, w0, P - BEAT) * (1 - _r_ramp(f, P + BEAT, w1))
    A = 0.55 * _RK
    th = lambda f: -2.5 * _RK - A * math.cos(TAU * (f - P) / BEAT) * (0.75 + 0.25 * math.cos(math.pi * (f - P) / (2 * BEAT)))
    _r_arm_pose(arm, side, w0, w1, env, th, lambda f: 0.25, extra=(P - BEAT, P, P + BEAT))
    lim = 1.25
    neck = _r_neck(root, head, (0.0, 0.0, 1.2))
    _r_nod(neck, w0, w1, pitch=lambda f: _RK * 0.3 * _r_bump(f, P, 4.0), yaw=lambda f: env(f) * max(-lim, min(lim, _r_dir(root, f))),
           scale=lambda f: (1 + 0.04 * _r_bump(f, P, 4.0),) * 2 + (1 - 0.06 * _r_bump(f, P, 4.0),), extra=(P,))
    return (name, 'glance back + wave x3', w0, P, w1, 'arm mean %.0f deg, swing +-%.0f deg, head yaw %.0f deg' % (math.degrees(2.5 * _RK), math.degrees(A), math.degrees(max(-lim, min(lim, _r_dir(root, P))))))


def _r_cheer(name, P):
    """Both arms go straight up (the bag overhead) on beat P, then down again by P + BEAT (neighbours walk close after that); the head tilts back."""
    root = bpy.data.objects[name]
    arms, head = _r_parts(root)
    w0, w1 = P - BEAT, P + BEAT
    env = lambda f: _r_ramp(f, P - BEAT, P - 1) * (1 - _r_ramp(f, P + 0.2 * BEAT, w1))
    th = lambda f: -(2.75 + 0.2 * _r_bump(f, P, 4.5)) * _RK
    for i, a in enumerate(arms):
        _r_arm_pose(a, 1 if i == 0 else -1, w0, w1, env, th, lambda f: 0.15, extra=(P,))
    neck = _r_neck(root, head, (0.0, 0.0, 1.2))
    _r_nod(neck, w0, w1, pitch=lambda f: -0.3 * _RK * env(f),
           scale=lambda f: (1 - 0.03 * _r_bump(f, P, 4.0),) * 2 + (1 + 0.05 * _r_bump(f, P, 4.0),), extra=(P,))
    return (name, 'cheer, both arms up', w0, P, w1, 'arms %.0f deg, head back %.0f deg' % (math.degrees(2.95 * _RK), math.degrees(0.3 * _RK)))


def _r_jump(name, P):
    """The kid jumps twice, apexes on beats P - BEAT and P: squash before take-off, stretch in the air, squash on landing; both arms fly up at each apex.
    One body empty (torso_hop_*) carries every part, so the whole kid hops (feet leave the ground by intent) and squashes about the feet."""
    root = bpy.data.objects[name]
    arms, head = _r_parts(root)
    A1, A2 = P - BEAT, P
    w0, w1 = A1 - 9, A2 + 10
    neck = _r_neck(root, head, (0.0, 0.0, 1.2))
    body = empty("torso_hop_" + name, (0, 0, 0))
    body.parent = root
    body.location = (0, 0, 0)
    for c in list(root.children):
        if c is not body:
            c.parent = body
    H = 0.50 * _RK                                   # local units; the kid root scale 0.78 makes it 0.39 m in the street
    tab = [(w0, 0, 0), (A1 - 6, 0, 1.0), (A1 - 3, 0.55, -0.7), (A1, 0.9, -0.2), (A1 + 3, 0.55, 0.0), (A1 + 6, 0, 1.0),
           (A2 - 3, 0.55, -0.7), (A2, 1.0, -0.2), (A2 + 3, 0.55, 0.0), (A2 + 6, 0, 1.0), (w1, 0, 0)]

    def sc(f):
        z, sq = _r_tab(f, tab)
        sz = 1 - 0.18 * sq if sq > 0 else 1 - 0.12 * sq
        sxy = 1 + 0.08 * sq if sq > 0 else 1 + 0.05 * sq
        return sxy, sxy, sz
    _r_write(body, 'location', 2, w0, w1, lambda f, b: H * _r_tab(f, tab)[0] if w0 < f < w1 else 0.0, extra=(A1, A2))
    for idx in (0, 1, 2):
        _r_write(body, 'scale', idx, w0, w1, lambda f, b, idx=idx: sc(f)[idx] if w0 < f < w1 else 1.0, extra=(A1, A2))
    up = lambda f: max(_r_bump(f, A1, 3.5), _r_bump(f, A2, 3.5))
    for i, a in enumerate(arms):
        _r_arm_pose(a, 1 if i == 0 else -1, w0, w1, up, lambda f: -2.6 * _RK, lambda f: 0.35, extra=(A1, A2))
    return (name, 'jump x2 (squash and stretch)', w0, P, w1, 'hop %.0f cm, arms %.0f deg' % (H * 0.78 * 100, math.degrees(2.6 * _RK)))


def _r_dog(P):
    """The dog keeps trotting (its location keys stay) but looks up at the camera: head yaw to the camera (limit 20 degrees: a wider turn brings the head into the owner's skirt box, which the dog already overlaps in the base path), head up 34 degrees at the accent, tail up and wagging (+-40 degrees, twice per beat)."""
    root = bpy.data.objects['dog']
    arms, head = _r_parts(root)
    w0, w1 = P - BEAT, P + 2 * BEAT
    env = lambda f: _r_ramp(f, P - BEAT, P - 2) * (1 - _r_ramp(f, P + 0.8 * BEAT, w1))
    lim = 0.35
    neck = _r_neck(root, head, (0.3, 0.0, 0.45))
    _r_nod(neck, w0, w1, pitch=lambda f: -(0.45 * env(f) + 0.15 * _r_bump(f, P, 4.5)) * _RK, yaw=lambda f: env(f) * max(-lim, min(lim, _r_dir(root, f))), extra=(P,))
    tail = next(c for c in root.children if c.name.startswith('dog_tail'))
    _r_write(tail, 'rotation_euler', 1, w0, w1, lambda f, b: (b + 0.8 * _RK * env(f)) if w0 < f < w1 else b)       # tail up 46 degrees
    # The base wag keys (BEAT / 8 apart, sine period BEAT / 4) all fall on sine zeros, so the base tail never moves. Here it wags +-40 degrees, twice per beat, extremes on beat and half beat.
    _r_write(tail, 'rotation_euler', 2, w0, w1, lambda f, b: (b + 0.7 * _RK * env(f) * math.cos(TAU * (f - BEAT0) / (BEAT / 2))) if w0 < f < w1 else b)
    return ('dog', 'looks up at the camera, tail up', w0, P, w1, 'head yaw %.0f deg (limit 20), up %.0f deg, tail up 46 deg, wag +-40 deg x2 per beat' % (math.degrees(max(-lim, min(lim, _r_dir(root, P)))), math.degrees(0.6 * _RK)))


_R_LOG = []
for _r_fn, _r_args in ((_r_bag, ('adultS1', 421.0)), (_r_jump, ('enter_candy_2', 508.5)), (_r_follow, ('teenS', 796.0)),
                       (_r_wave, ('leave_comic_2', 846.0)), (_r_cheer, ('leave_train_0', 958.5)), (_r_wave, ('enter_book_2', 383.5))):
    if _r_args[0] in bpy.data.objects:
        _R_LOG.append(_r_fn(*_r_args))
    else:
        print('react: missing', _r_args[0])
if 'dog' in bpy.data.objects:
    _R_LOG.append(_r_dog(983.5))
for _r_l in _R_LOG:
    print('REACT %-14s %-30s start %.1f peak %.1f end %.1f  %s' % _r_l)
at(_r_cur)
