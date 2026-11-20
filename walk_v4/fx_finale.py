# fx_finale.py - a warm last shot: a gentle shower of cookie crumbs / sprinkles / confetti, then the title card "Kevin Cookie Company".
# Run by build_neighborhood_walk_v2.py through the WALK_FX hook (uses its globals). Nothing is simulated: every piece has keyframes.
# Timeline (frames): the pieces exist from FIN_T0 (a beat frame, start of the bar "outro 2: last chord") to the last frame; before that every
# piece and the title rig have hide_render = True (keyed), so frames before FIN_T0 are identical to a render without this effect and cost nothing.
# Title: finale.json {"title_frame": N} (a beat frame, read here, also read by the sound agent): the plate pops in over 12 frames, holds to the end.
# Pieces: spawned just ABOVE the top edge of the picture (no pop-in), fall slowly in the road column, sway on a 2-beat period (beat grid, scaled by PUNCH),
# tumble slowly, and lie on the road when they land. Pieces that would pass in front of the title plate after it appears are rejected when the table is built.
import json as _json

FIN_T0 = 1271                    # = BEAT0 + 101 * BEAT (a beat frame), start of the last bar
FIN_N = 250                      # number of pieces
try:
    FIN_TITLE = int(_json.load(open(os.path.join(OUT, 'finale.json')))['title_frame'])
except Exception:
    FIN_TITLE = 1346             # = BEAT0 + 107 * BEAT
FIN_TEXT = "Kevin Cookie Company"
_TAN_H = 18.0 / LENS             # horizontal half field of view (36 mm sensor)
_TAN_V = _TAN_H * 9.0 / 16.0
_FIN_D = 4.0                     # title plate distance from the camera (m)
_FIN_CY = 0.95                   # title plate centre height above the view axis (m, in the camera frame)
_FIN_W, _FIN_H = 5.1, 0.85       # plate size (m)
_ROAD = (-11.2, -6.0)            # pieces stay in the road column: no sidewalk, person, tree or lamp below them
at(Matrix.Identity(4))


def _pose(f):
    """Camera location and axes at integer frame f (same formulas as the camera keys in the build script; _STEP, _XB are the build script's)."""
    x_ = CAM_X[max(0, min(len(CAM_X) - 1, int(f) - 1))]
    psi_ = psi_of(x_)
    y_ = Y_MID + Y_AMP * max(-1.0, min(1.0, psi_ / PSI_SECOND)) + 0.012 * PUNCH * math.sin(TAU * (x_ - _XB) / (2 * _STEP))
    z_ = CAM_Z - 0.010 * PUNCH * math.cos(TAU * (x_ - _XB) / _STEP)
    fwd = Vector((math.cos(psi_) * math.cos(PITCH), math.sin(psi_) * math.cos(PITCH), math.sin(PITCH)))
    right = fwd.cross(Vector((0, 0, 1))).normalized()
    return Vector((x_, y_, z_)), fwd, right, right.cross(fwd)


def _proj(p, pose):
    """(u, v, depth): u, v are -1..1 across the half width / half height of the picture."""
    loc, fwd, right, up = pose
    r = p - loc
    d = r.dot(fwd)
    if d < 0.05:
        return None
    return r.dot(right) / (d * _TAN_H), r.dot(up) / (d * _TAN_V), d


# ---- ground height: the road top (measured with a ray cast on the plain build: -0.02 m). A constant, because other effects (haze volume) can be hit by a ray.
_GROUND = -0.02

# ---- materials
_PAL = ['#FF7FA8', '#FFD166', '#FF9E6B', '#FF5C8A', '#E63946', '#C8B6F2', '#9BE5B5', '#4FC9BE', '#FFF6E6', '#FFD166', '#FF7FA8']
_BRN = ['#E3A25A', '#B9743F', '#6B3E26', '#F6D6A8']
_mc = {}


def _fmat(h, st=0.45):
    if (h, st) not in _mc:
        _mc[(h, st)] = M(h, 0.7, emit=h, strength=st)
    return _mc[(h, st)]


# ---- shared meshes (unit size): one mesh per (shape, colour); every piece of that kind links to it
def _bm_mesh(name, bm, mats):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = False
    for m in mats:
        me.materials.append(m)
    return me


def _mesh_box(name, sx, sy, sz, m):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    return _bm_mesh(name, bm, [m])


def _mesh_hex(name, m):
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, cap_tris=False, segments=6, radius=0.5)
    r = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    bmesh.ops.translate(bm, vec=(0, 0, 0.08), verts=[v for v in r['geom'] if isinstance(v, bmesh.types.BMVert)])
    return _bm_mesh(name, bm, [m])


def _mesh_crumb(name, m, seed):
    rnd = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.5)
    for v in bm.verts:
        v.co = Vector((v.co.x * (1 + rnd.uniform(-0.25, 0.25)), v.co.y * (1 + rnd.uniform(-0.25, 0.25)), v.co.z * (0.65 + rnd.uniform(-0.2, 0.2))))
    return _bm_mesh(name, bm, [m])


def _mesh_cookie(name):
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, cap_tris=False, segments=9, radius=0.5)
    r = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    bmesh.ops.translate(bm, vec=(0, 0, 0.2), verts=[v for v in r['geom'] if isinstance(v, bmesh.types.BMVert)])
    for f in bm.faces:
        f.material_index = 0
    for (cx, cy) in ((0.14, 0.1), (-0.17, 0.02), (0.0, -0.2)):
        g = bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.09)
        vs = [v for v in g['verts']]
        bmesh.ops.translate(bm, vec=(cx, cy, 0.2), verts=vs)
        for f in {f for v in vs for f in v.link_faces}:
            f.material_index = 1
    return _bm_mesh(name, bm, [_fmat('#E3A25A', 0.5), _fmat('#4B2A1E', 0.3)])


_MESH = {}


def _get_mesh(shape, col, seed):
    key = (shape, col)
    if key not in _MESH:
        nm = 'fin_%s_%s' % (shape, col.lstrip('#'))
        if shape == 'conf':
            _MESH[key] = _mesh_box(nm, 1.0, 0.62, 0.05, _fmat(col))
        elif shape == 'spr':
            _MESH[key] = _mesh_box(nm, 1.0, 0.2, 0.2, _fmat(col))
        elif shape == 'hex':
            _MESH[key] = _mesh_hex(nm, _fmat(col))
        elif shape == 'crumb':
            _MESH[key] = _mesh_crumb(nm, _fmat(col, 0.3), seed)
        else:
            _MESH[key] = _mesh_cookie(nm)
    return _MESH[key]


# ---- the table of pieces (deterministic, built once)
_poses = {f: _pose(f) for f in range(FIN_T0, FRAMES + 1)}
_rng = random.Random(2026)
_TH = 2.0 * BEAT                                                     # sway period: 2 beats = 25 frames
_FSTEP = BEAT / 4                                                     # key spacing (3.125 frames)
_PLATE_U = 0.5 * _FIN_W / (_FIN_D * _TAN_H) + 0.06                   # half width of the plate in picture units (+ margin)
_PLATE_V = (_FIN_CY / (_FIN_D * _TAN_V), 0.5 * _FIN_H / (_FIN_D * _TAN_V) + 0.08)   # centre and half height (+ margin)
# spawn frame distribution: a trickle at the start, full shower from about 1330, a little less at the very end (pieces spawned late hardly enter the picture)
_wts = [(f, (0.75 + 0.25 * min(1.0, (f - FIN_T0) / 30.0) + (0.5 if 1295 <= f < 1350 else 0.0)) * (1.0 if f < 1400 else 0.6)) for f in range(FIN_T0, 1425)]
_tot = sum(w for _, w in _wts)


def _pick_spawn():
    r = _rng.random() * _tot
    for f, w in _wts:
        r -= w
        if r <= 0:
            return f
    return _wts[-1][0]


def _make_piece(i):
    for _try in range(400):
        f0 = _pick_spawn()
        shape = _rng.choices(['conf', 'hex', 'spr', 'crumb', 'cookie'], [30, 22, 22, 18, 8])[0]
        col = _rng.choice(_BRN if shape == 'crumb' else _PAL)
        dd = _rng.random()      # depth of the piece along the view axis at spawn: a few very near (large), most 2.5 - 9 m, some far (small)
        d0 = _rng.uniform(1.3, 2.5) if dd < 0.10 else (_rng.uniform(2.5, 5.0) if dd < 0.42 else (_rng.uniform(5.0, 9.0) if dd < 0.80 else _rng.uniform(9.0, 15.0)))
        size = {'conf': 0.2, 'hex': 0.17, 'spr': 0.26, 'crumb': 0.15, 'cookie': 0.25}[shape] * _rng.uniform(0.8, 1.3) * (1 + 0.035 * d0)
        size = min(size, 0.10 * d0)                                 # a near piece is at most about 110 px long in a 1080p picture at spawn
        pose0 = _poses[f0]
        # lateral position in the road column, inside the picture at spawn
        y = _rng.uniform(*_ROAD)
        loc, fwd, right, up = pose0
        u0 = (y - loc.y - fwd.y * d0) / (d0 * _TAN_H * right.y)
        if abs(u0) > 0.97:
            continue
        v0 = 1.0 + 0.1 + 0.8 * size / (d0 * _TAN_V)             # just above the top edge: the piece enters from above, no pop
        p0 = loc + fwd * d0 + right * (u0 * d0 * _TAN_H) + up * (v0 * d0 * _TAN_V)
        vz = _rng.uniform(0.045, 0.075)                           # fall speed m per frame (1.1 - 1.8 m/s)
        vwx = _rng.uniform(0.025, 0.045)                          # drift along the street, with the walker (a breeze from behind), m per frame
        amp = _rng.uniform(0.12, 0.30) * PUNCH / 2.5              # sway amplitude (m)
        ph = _rng.choice((0.5, -0.5)) * math.pi + _rng.uniform(-0.4, 0.4)   # sway extremes fall near the beats (half of the pieces swing left on the beat, half right)
        z_land = _GROUND + 0.6 * size * (0.25 if shape in ('conf', 'hex', 'cookie') else 0.5) + 0.01
        # sample the path on the key grid; stop when it lands
        rot0 = [_rng.uniform(0, TAU) for _ in range(3)]
        w = [_rng.choice((-1, 1)) * _rng.uniform(0.018, 0.075) for _ in range(3)]
        wob = _rng.uniform(0.25, 0.55)
        fr, pts, land = [], [], None
        f = float(f0)
        ok = True
        while f <= FRAMES + 1e-6:
            t = f - f0
            th = TAU * (f - BEAT0) / _TH + ph
            z = p0.z - vz * t + 0.03 * PUNCH / 2.5 * math.cos(TAU * (f - BEAT0) / BEAT)
            near = max(0.0, min(1.0, (z - z_land) / 0.7))          # sway dies down just before landing
            if z <= z_land:
                z, land = z_land, f
            x = p0.x + vwx * t + 0.5 * amp * near * math.sin(th + 1.7)
            yy = p0.y + amp * near * math.sin(th)
            fr.append(f)
            pts.append((x, yy, z, rot0[0] + w[0] * t + wob * near * math.sin(th + 0.9), rot0[1] + w[1] * t + wob * near * math.cos(th), rot0[2] + w[2] * t))
            if land is not None:
                break
            f += _FSTEP
        # the column must be free: the road only (no obstacle table needed), keep a margin to the road edges
        if any(not (_ROAD[0] - 0.5 <= q[1] <= _ROAD[1] + 0.5) for q in pts):
            continue
        # the string lights and pennants across the street hang at x = 25 (z 2.5 - 4.0): keep pieces out of that slab
        if any(24.3 - size < q[0] < 25.7 + size and 2.2 < q[2] < 4.3 for q in pts):
            continue
        # the parked blue car (x 43, y -6) stands at the far end of the road: keep out of its box
        if any(40.8 - size < q[0] < 45.2 + size and -7.2 - size < q[1] < -4.8 + size and q[2] < 1.7 + size for q in pts):
            continue
        # per frame: no piece closer than 1.8 m or longer than 150 px (1080p) inside the picture; no piece in front of the title plate after it appears
        # (depth < plate depth + margin, inside the plate rectangle)
        bad = False
        for ff in range(f0, min(FRAMES, int(fr[-1])) + 1):
            k = min(len(fr) - 1, max(0, int((ff - f0) / _FSTEP)))
            pr = _proj(Vector(pts[k][:3]), _poses[ff])
            if pr is None:
                continue
            u, v, dep = pr
            if abs(u) < 1.1 and abs(v) < 1.1 and (dep < 1.8 or size / (dep * _TAN_H) * 960 > 150):
                bad = True
                break
            if ff >= FIN_TITLE - 3 and dep < _FIN_D + 0.6 + size and abs(u) < _PLATE_U + size / (dep * _TAN_H) and abs(v - _PLATE_V[0]) < _PLATE_V[1] + size / (dep * _TAN_V):
                bad = True
                break
        if bad:
            continue
        return dict(f0=f0, shape=shape, col=col, size=size, fr=fr, pts=pts, seed=i)
    raise RuntimeError('finale: no free piece found')


FIN_PIECES = []
for _i in range(FIN_N):
    _pc = _make_piece(_i)
    _fme = _get_mesh(_pc['shape'], _pc['col'], _pc['seed'])
    _o = bpy.data.objects.new("fin_%s_%d" % (_pc['shape'], _i), _fme)
    scene.collection.objects.link(_o)
    _o.visible_shadow = False
    _o.scale = (_pc['size'],) * 3
    # hide_render keys: hidden until one frame before the spawn, shown from the spawn frame (constant interpolation, boolean)
    for _fr, _hv in ((_pc['f0'] - 1, True), (_pc['f0'], False)):
        _o.hide_render = _hv
        _o.keyframe_insert('hide_render', frame=_fr)
    _ad = _o.animation_data
    _cb = _ad.action.layers[0].strips[0].channelbag(_ad.action_slot)
    _F = _pc['fr']
    for _path, _off in (('location', 0), ('rotation_euler', 3)):
        for _ax in range(3):
            _fc = _cb.fcurves.new(_path, index=_ax)
            _fc.keyframe_points.add(len(_F))
            _fc.keyframe_points.foreach_set('co', [v for _f, _q in zip(_F, _pc['pts']) for v in (_f, _q[_off + _ax])])
            _fc.keyframe_points.foreach_set('interpolation', [1] * len(_F))     # LINEAR
            _fc.update()
    FIN_PIECES.append(_pc)

# ---- the title card: camera-parented like the name tags; plate + text + two cookie dots; scale pop over 12 frames from FIN_TITLE
_PLATE = M('#4A2A1C', 0.7, emit='#4A2A1C', strength=0.6)
_RIM = M('#FFF6E6', 0.6, emit='#FFF6E6', strength=0.6)
_INKT = M('#FFD7E4', 0.5, emit='#FFD7E4', strength=0.3)
_frig = empty("finale_title")
_frig.parent = cam
_frig.location = (0.0, _FIN_CY, -_FIN_D)
_kids = [box("fin_rim", -_FIN_W / 2 - 0.08, _FIN_W / 2 + 0.08, -_FIN_H / 2 - 0.08, _FIN_H / 2 + 0.08, -0.12, -0.06, _RIM, shadow=False),
         box("fin_plate", -_FIN_W / 2, _FIN_W / 2, -_FIN_H / 2, _FIN_H / 2, -0.09, -0.02, _PLATE, shadow=False)]
_tx = text(FIN_TEXT, (0.0, 0.0, 0.02), 0.6, _INKT, rot=(0, 0, 0), extrude=0.04, maxw=_FIN_W - 1.3)
_kids.append(_tx)
_dough = M('#E3A25A', 0.8, emit='#E3A25A', strength=0.5)
_n0 = len(_new)
for _fsx in (-_FIN_W / 2 + 0.34, _FIN_W / 2 - 0.34):
    cookie("fin_dot", (_fsx, 0.0, -0.02), 0.2, 0.08, 'Z', _dough, M('#4B2A1E', 0.8, emit='#4B2A1E', strength=0.2), nchips=3, seed=3)
_kids += _new[_n0:]
for _k in _kids:
    _k.parent = _frig
    if _k.type == 'MESH':
        _k.visible_shadow = False
for _fr, _hv in ((FIN_TITLE - 1, True), (FIN_TITLE, False)):
    _frig.hide_render = _hv
    _frig.keyframe_insert('hide_render', frame=_fr)
for _k in _kids:                       # hide_render is not inherited by children in all cases: key it on every part too
    for _fr, _hv in ((FIN_TITLE - 1, True), (FIN_TITLE, False)):
        _k.hide_render = _hv
        _k.keyframe_insert('hide_render', frame=_fr)
for (_fr, _v) in ((FIN_TITLE, 0.001), (FIN_TITLE + 8, 1.07), (FIN_TITLE + 12, 1.0)):
    kf(_frig, 'scale', None, _fr, (_v, _v, _v), 'BEZIER')
print('finale: %d pieces, title at %d, ground z %.3f' % (len(FIN_PIECES), FIN_TITLE, _GROUND))
