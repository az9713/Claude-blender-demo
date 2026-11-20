# fx_moments.py - one small signature moment per shop, locked to the beat (hit frames in moments.json, on the beat grid).
# Run by build_neighborhood_walk_v2.py through the WALK_FX hook (uses its globals). No simulation, no cache: keyframes only.
# Every moment is one rig (an empty named mom_<shop>) with low-poly flat-colour parts. The props (furniture) are STATIC and visible for the whole video:
# nothing grows or shrinks. Only the ACTION parts (pages, lid, candies, steam, sprinkles, fish, bubbles, rings, sparks, coin, wheel, bell) have keys.
# Timeline per shop (u = frame - hit): u -6..-1 anticipation (wind-up), u 0 peak, u 0..12 settle, back to rest by u 18.
# Transient parts (steam, sprinkles, sparks, rings ...) scale up from 0 over several frames and down to 0, and are hidden (hide_render keys) outside.
# Toy, ice, candy, bike and arcade repeat once with the peak at hit+25 (rest again by hit+43).
# Every part has its own keys in the rig frame; the rig frame is placed in the shop frame (shop_matrix) and turned to the camera.
_mm_MJ = json.load(open(os.path.join(OUT, 'moments.json'), encoding='utf-8'))
_mm_HIT = {s_['shop']: int(s_['hit']) for s_ in _mm_MJ['shops']}
_mm_REP = ('toy', 'ice', 'candy', 'bike', 'arcade')
_MM_K = min(PUNCH / 2.5, 1.4)                               # amplitude factor: 1.0 at the default PUNCH 2.5
MOM_RIGS = {}                                              # shop kind -> rig (read by the measuring probes)
bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'


def _mm_mpm(c, e=0.3, r=0.6):
    """Flat pastel material with a little own light so it reads in shade (same look as the notes)."""
    return M(c, r, emit=c, strength=e)


# ---------- small curves ----------
def _mm_ss(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _mm_act(u):
    """Action intensity: 0 before u=-4, smooth rise to 1 at u=0 (the hit), smooth fall to 0 at u=12."""
    if -4 <= u < 0:
        return _mm_ss((u + 4) / 4.0)
    if 0 <= u <= 12:
        return 1 - _mm_ss(u / 12.0)
    return 0.0


def _mm_ant(u):
    """Anticipation: a dip that peaks at u=-3.5 and is zero outside -6..-1."""
    return math.sin(math.pi * (u + 6) / 5.0) if -6 <= u <= -1 else 0.0


def _mm_bellS(u, tot, half=7.0):
    """Distance travelled when the speed is cos^2 centred on u=0 with half-width `half`; total `tot` over the whole bell."""
    if u <= -half:
        return 0.0
    if u >= half:
        return tot
    return tot * (((u + half) / 2.0) + (half / (2 * math.pi)) * math.sin(math.pi * u / half)) / half


def _mm_blend(m):
    """Alpha-blended instead of dithered transparency (less noise on the glass)."""
    try:
        m.surface_render_method = 'BLENDED'
    except Exception:
        pass
    return m


def _mm_pop(hu, up=3.0, down=9.0):
    """Burst envelope: 0 at hu = -up, exactly 1 at hu = 0 (the hit), back to 0 at hu = down."""
    if -up <= hu < 0:
        return _mm_ss((hu + up) / up)
    if 0 <= hu <= down:
        return 1 - _mm_ss(hu / down)
    return 0.0


def _mm_popin(t):
    """Ease-out with a small overshoot, t 0..1."""
    t = max(0.0, min(1.0, t))
    c1 = 1.0
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# ---------- geometry helpers: parts are built in a clean frame at the origin, then parented to the rig ----------
def _mm_mk(o, parent, loc=None, rot=None):
    o.parent = parent
    if loc is not None:
        o.location = loc
    if rot is not None:
        o.rotation_euler = rot
    return o


def _mm_D(name, c, r, h, m, parent, seg=8, axis='Z', rot=None, taper=1.0, shadow=True):
    o = disc(name, (0, 0, 0), r, h, m, seg=seg, axis=axis, taper=taper)
    if not shadow:
        o.visible_shadow = False
    return _mm_mk(o, parent, c, rot)


def _mm_B(name, c, s, m, parent, rot=None, shadow=True):
    o = box(name, -s[0] / 2, s[0] / 2, -s[1] / 2, s[1] / 2, -s[2] / 2, s[2] / 2, m, shadow=shadow)
    return _mm_mk(o, parent, c, rot)


def _mm_I(name, c, s, m, parent, sub=1, shadow=True):
    o = ico(name, (0, 0, 0), s, m, sub=sub, shadow=shadow)
    return _mm_mk(o, parent, c)


def _mm_E(name, parent, loc=(0, 0, 0), rot=(0, 0, 0)):
    e = empty(name)
    e.parent = parent
    e.location = loc
    e.rotation_euler = rot
    return e


def _mm_P(name, pts, t, m, parent, c=(0, 0, 0), rot=None, shadow=False):
    """Prism from an XZ polygon, thickness t centred on y=0."""
    o = tri_prism(name, pts, t, m, y0=-t / 2, shadow=shadow)
    return _mm_mk(o, parent, c, rot)


def _mm_torus(name, R, r, m, parent, nu=10, nv=5):
    bm = bmesh.new()
    vs = []
    for i in range(nu):
        a = TAU * i / nu
        row = []
        for j in range(nv):
            b = TAU * j / nv
            rr = R + r * math.cos(b)
            row.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), r * math.sin(b))))
        vs.append(row)
    for i in range(nu):
        for j in range(nv):
            bm.faces.new([vs[i][j], vs[(i + 1) % nu][j], vs[(i + 1) % nu][(j + 1) % nv], vs[i][(j + 1) % nv]])
    o = build(name, bm, m, shadow=False)
    return _mm_mk(o, parent)


def _mm_band(name, pts, w, z0, z1, m, parent):
    """Closed flat band (track) along a closed centre line pts = [(x, y, heading)], width w."""
    bm = bmesh.new()
    n = len(pts)
    ot, it, ob, ib = [], [], [], []
    for (x, y, th) in pts:
        nx, ny = -math.sin(th), math.cos(th)
        ot.append(bm.verts.new((x + nx * w / 2, y + ny * w / 2, z1)))
        it.append(bm.verts.new((x - nx * w / 2, y - ny * w / 2, z1)))
        ob.append(bm.verts.new((x + nx * w / 2, y + ny * w / 2, z0)))
        ib.append(bm.verts.new((x - nx * w / 2, y - ny * w / 2, z0)))
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([ot[i], ot[j], it[j], it[i]])
        bm.faces.new([ob[i], ob[j], ot[j], ot[i]])
        bm.faces.new([it[i], it[j], ib[j], ib[i]])
    o = build(name, bm, m, shadow=False)
    return _mm_mk(o, parent)


def _mm_K(o, f, loc=None, rot=None, scl=None):
    """Key the given channels at frame f (LINEAR)."""
    if loc is not None:
        o.location = loc
        o.keyframe_insert('location', frame=f)
    if rot is not None:
        o.rotation_euler = rot
        o.keyframe_insert('rotation_euler', frame=f)
    if scl is not None:
        o.scale = (scl, scl, scl) if isinstance(scl, (int, float)) else scl
        o.keyframe_insert('scale', frame=f)


def _mm_desc(o):
    out_ = []
    for c_ in o.children:
        out_.append(c_)
        out_ += _mm_desc(c_)
    return out_


def _mm_cam_local(S, f):
    """Camera position at frame f in the shop frame (x along the front, y negative toward the street)."""
    x = CAM_X[max(0, min(len(CAM_X) - 1, int(f) - 1))]
    psi = psi_of(x)
    y = Y_MID + Y_AMP * max(-1.0, min(1.0, psi / PSI_SECOND))
    return shop_matrix(S['cx'], S['side']).inverted() @ Vector((x, y, CAM_Z))


def _mm_shop(kind):
    return next(S_ for S_ in SHOP_LIST if S_['kind'] == kind)


class _mm_Fx:
    """One moment: rig + timeline. anim(self, f, u, u2) is called for every frame of the window and keys the parts."""

    def __init__(self, kind, anchor, face=0.7, side_on=False, big=1.0, yaw_extra=0.0):
        self.kind, self.S, self.hit = kind, _mm_shop(kind), _mm_HIT[kind]
        self.rep = kind in _mm_REP
        self.last = self.hit + (43 if self.rep else 18)               # last frame of the action (transients are gone here)
        at(Matrix.Identity(4))
        self.rig = empty("mom_" + kind)
        self.rig['mm_face'], self.rig['mm_side'], self.rig['mm_yawx'] = face, int(side_on), yaw_extra
        self.anchor, self.big = Vector(anchor), big
        c = _mm_cam_local(self.S, self.hit)
        d = Vector((c.x - anchor[0], c.y - anchor[1], 0))
        if side_on:       # the canonical +X axis points across the view direction, toward the street side
            px, py = -d.y, d.x
            if py > 0:
                px, py = -px, -py
            self.yaw = math.atan2(py, px) + yaw_extra
        else:             # the canonical front (-Y) turns toward the camera by `face`
            self.yaw = face * math.atan2(d.x, -d.y) + yaw_extra
        self.cam = c
        dr = Matrix.Rotation(-self.yaw, 3, 'Z') @ d                      # the camera direction in the rig frame
        self.camy = 1.0 if dr.y > 0 else -1.0

    def done(self, anim, trans=(), pulse=()):
        rig = self.rig
        if self.anchor.z > 4.5 and self.kind not in ('comic', 'bike'):    # facade moments: two wood arms hold the prop to the wall (rig y of the wall = -anchor.y)
            g = -self.anchor.y
            for ax_ in (-0.6, 0.6):
                _mm_B("wall_arm", (ax_, g / 2, -0.62), (0.1, g, 0.1), _mm_mpm('#7A4B2A'), rig)
        rig.matrix_world = shop_matrix(self.S['cx'], self.S['side']) @ Matrix.Translation(self.anchor) @ Matrix.Rotation(self.yaw, 4, 'Z') @ Matrix.Scale(self.big, 4)
        bpy.context.view_layer.update()
        self.run(anim, trans, pulse)

    def run(self, anim, trans=(), pulse=()):
        """Key the action. `trans` = transient objects (hidden outside the window, children included); `pulse` = objects that get a small scale punch at the hit."""
        rig, hit = self.rig, self.hit
        f0 = hit - 24
        tp = []
        for o in trans:
            tp += [o] + _mm_desc(o)
        tp = [o for o in tp if o.type in ('MESH', 'CURVE', 'FONT')]
        for f in range(f0, self.last + 2):
            u, u2 = f - hit, f - (hit + 25)
            pul = _MM_K * (0.18 * math.exp(-(u / 3.2) ** 2) - 0.05 * _mm_ant(u))
            if self.rep:
                pul += _MM_K * (0.18 * math.exp(-(u2 / 3.2) ** 2) - 0.05 * _mm_ant(u2))
            for o in pulse:
                _mm_K(o, f, scl=1 + pul)
            anim(self, f, u, u2)
        for o in tp:                                             # hidden before f0, visible f0 .. last, hidden after
            for f, v in ((f0 - 1, True), (f0, False), (self.last, False), (self.last + 1, True)):
                o.hide_render = v
                o.keyframe_insert('hide_render', frame=f)
        MOM_RIGS[self.kind] = rig


def _mm_jit(seed, n):
    r_ = random.Random(seed)
    return [r_.random() for _ in range(n)]


# ======================================================================
# 1. TOY: a toy train circles a small track mounted on the facade (the upper-window stage)
# ======================================================================
def _mm_stad(s, L, R):
    P = 2 * L + 2 * math.pi * R
    s = s % P
    if s < L:
        return (-L / 2 + s, -R, 0.0)
    s -= L
    if s < math.pi * R:
        a = s / R
        return (L / 2 + R * math.sin(a), -R * math.cos(a), a)
    s -= math.pi * R
    if s < L:
        return (L / 2 - s, R, math.pi)
    s -= L
    a = s / R
    return (-L / 2 - R * math.sin(a), R * math.cos(a), math.pi + a)


def _mm_loco(parent, s=1.0, body='#F25C54', roof='#FFD166'):
    """Toy locomotive, forward = +X, origin at rail level. Returns (root, wheels)."""
    r = _mm_E("loco", parent)
    _mm_B("loco_chassis", (0, 0, 0.12 * s), (0.62 * s, 0.34 * s, 0.1 * s), _mm_mpm('#5C4E7A'), r)
    _mm_D("loco_boiler", (0.1 * s, 0, 0.3 * s), 0.15 * s, 0.4 * s, _mm_mpm(body), r, seg=8, rot=(0, math.pi / 2, 0))
    _mm_B("loco_cab", (-0.2 * s, 0, 0.3 * s), (0.22 * s, 0.34 * s, 0.34 * s), _mm_mpm('#FFF6E6'), r)
    _mm_B("loco_roof", (-0.2 * s, 0, 0.5 * s), (0.28 * s, 0.4 * s, 0.05 * s), _mm_mpm(roof), r)
    _mm_D("loco_chim", (0.24 * s, 0, 0.5 * s), 0.05 * s, 0.2 * s, _mm_mpm('#7A4B2A'), r, seg=6)
    _mm_D("loco_chim_top", (0.24 * s, 0, 0.62 * s), 0.08 * s, 0.05 * s, _mm_mpm(roof), r, seg=6)
    _mm_I("loco_lamp", (0.31 * s, 0, 0.3 * s), 0.05 * s, _mm_mpm('#FFF6E6', 1.5), r)
    _mm_P("loco_catcher", [(0.3 * s, 0.17 * s), (0.42 * s, 0.05 * s), (0.3 * s, 0.05 * s)], 0.3 * s, _mm_mpm('#FFD166'), r)
    ws = []
    for wx in (-0.2, 0.2):
        for wy in (-0.18, 0.18):
            ws.append(_mm_D("loco_wheel", (wx * s, wy * s, 0.1 * s), 0.1 * s, 0.05 * s, _mm_mpm('#FFD166'), r, seg=8, axis='Y'))
    return r, ws


def _mm_wagon(parent, col, s=1.0):
    r = _mm_E("wagon", parent)
    _mm_B("wagon_body", (0, 0, 0.2 * s), (0.46 * s, 0.32 * s, 0.18 * s), _mm_mpm(col), r)
    _mm_B("wagon_rim", (0, 0, 0.3 * s), (0.5 * s, 0.36 * s, 0.03 * s), _mm_mpm('#FFF6E6'), r)
    _mm_I("wagon_load", (0, 0, 0.36 * s), 0.1 * s, _mm_mpm('#FF7FA8'), r)
    for wx in (-0.14, 0.14):
        for wy in (-0.17, 0.17):
            _mm_D("wagon_wheel", (wx * s, wy * s, 0.08 * s), 0.08 * s, 0.04 * s, _mm_mpm('#FFD166'), r, seg=8, axis='Y')
    return r


def _mm_up(kind, x, y, dz=0.6):
    """Anchor at an upper window of the shop (x about +-3.6 .. 4.0, just off the wall; z = window sill + dz). The spot comes from fx_logs/moments/search.py."""
    S_ = _mm_shop(kind)
    return (x, y, S_['H'] - 2.4 + dz)


def _mm_build_toy():
    fx = _mm_Fx('toy', _mm_up('toy', -4.0, -0.55), face=0.35, big=1.0)
    _mm_B("loop_back", (0, 0.05, 0), (2.6, 0.06, 2.2), _mm_mpm('#FFF6E6'), fx.rig)
    _mm_B("loop_back_rim", (0, 0.03, 0), (2.8, 0.04, 2.4), _mm_mpm('#9BE5B5'), fx.rig)
    pl = _mm_E("loop_plane", fx.rig, (0, -0.06, 0), (math.pi / 2, 0, 0))            # the track plane stands on the wall; its +Z points at the street
    L, R = 0.45, 0.75
    n = 36
    P = 2 * L + 2 * math.pi * R
    pts = [_mm_stad(P * i / n, L, R) for i in range(n)]
    _mm_band("track_bed", pts, 0.42, 0.0, 0.04, _mm_mpm('#E3A25A'), pl)
    for dd in (0.14, -0.14):
        _mm_band("track_rail", [(x - math.sin(th) * dd, y + math.cos(th) * dd, th) for (x, y, th) in pts], 0.04, 0.04, 0.08, _mm_mpm('#DDE3EA'), pl)
    tr = _mm_E("train", pl, (0, 0, 0.1))
    loco, wheels = _mm_loco(tr, 1.0)
    w1 = _mm_wagon(tr, '#4FC9BE')
    w2 = _mm_wagon(tr, '#C8B6F2')
    trains = [(loco, 0.0), (w1, -0.62), (w2, -1.12)]
    s_rest = P * 0.62

    def anim(self, f, u, u2):
        S_ = s_rest + _mm_bellS(u, 5.4) - 0.3 * _mm_ant(u) + _mm_bellS(u2, 5.4) - 0.3 * _mm_ant(u2)
        hop = _MM_K * 0.05 * max(_mm_act(u), _mm_act(u2))
        for o, off in trains:
            x, y, th = _mm_stad(S_ + off, L, R)
            _mm_K(o, f, loc=(x, y, hop * (1 if o is loco else 0.6)), rot=(0, 0, th))
        for w in wheels:
            _mm_K(w, f, rot=(0, -S_ / 0.1, 0))
    fx.done(anim)


# ======================================================================
# 2. BOOK: pages flip and flutter open on a lectern
# ======================================================================
def _mm_build_book():
    fx = _mm_Fx('book', (-0.4, -2.15, 0.15), face=0.6, big=1.3)
    wood, cover = _mm_mpm('#C98A5B'), _mm_mpm('#2A6F97')
    for sx in (-0.42, 0.42):
        _mm_B("lect_leg", (sx, 0, 0.45), (0.06, 0.5, 0.9), wood, fx.rig)
    _mm_B("lect_base", (0, 0, 0.04), (1.0, 0.7, 0.08), wood, fx.rig)
    _mm_B("lect_back", (0, 0.2, 0.55), (0.8, 0.05, 0.6), wood, fx.rig)
    tilt = _mm_E("lect_tilt", fx.rig, (0, 0, 1.0), (0.5, 0, 0))
    _mm_B("lect_top", (0, 0, 0.0), (1.1, 0.7, 0.05), wood, tilt)
    _mm_B("bk_cover_l", (-0.27, 0, 0.045), (0.5, 0.64, 0.035), cover, tilt)
    _mm_B("bk_cover_r", (0.27, 0, 0.045), (0.5, 0.64, 0.035), cover, tilt)
    _mm_B("bk_block_l", (-0.24, 0, 0.075), (0.44, 0.58, 0.03), _mm_mpm('#FFF6E6'), tilt)
    _mm_B("bk_block_r", (0.24, 0, 0.085), (0.44, 0.58, 0.05), _mm_mpm('#FFF6E6'), tilt)
    cols = ['#FF7FA8', '#9BE5B5', '#7FB5FF', '#FFD166', '#C8B6F2']
    hinges = []
    for i, c in enumerate(cols):
        h = _mm_E("page_hinge", tilt, (0, 0, 0.115 + 0.006 * i))
        _mm_B("page", (0.23, 0, 0.0), (0.44, 0.58, 0.012), _mm_mpm(c, 0.35), h)
        hinges.append(h)
    loose = []
    for i, c in enumerate(('#FFD166', '#FF7FA8', '#9BE5B5')):
        loose.append(_mm_B("loose_page", (0, 0, 1.2), (0.3, 0.02, 0.4), _mm_mpm(c, 0.35), fx.rig))
    rj = _mm_jit(5, 12)

    def anim(self, f, u, u2):
        for i, h in enumerate(hinges):
            t = (u - (-6 + 1.5 * i)) / 9.0
            th = math.pi * _mm_ss(t)
            wob = 0.22 * math.sin(math.pi * max(0.0, min(1.0, t))) * math.sin(t * 9 + i)
            _mm_K(h, f, rot=(wob, -th, 0.12 * math.sin(math.pi * max(0.0, min(1.0, t))) * (1 if i % 2 else -1)))
        for i, p in enumerate(loose):
            t = (u - (-4 + 1.5 * i)) / 15.0
            tt = max(0.0, min(1.0, t))
            vis = math.sin(math.pi * tt) ** 0.6 if 0 < t < 1 else 0.0
            x = (-0.25 + 0.25 * i) + 0.35 * math.sin(tt * 5 + i) * tt
            z = 1.05 + 1.0 * tt
            _mm_K(p, f, loc=(x, -0.2 * tt, z), rot=(0.7 * math.sin(tt * 7 + i), 0.9 * math.sin(tt * 4 + 2 * i), tt * 3 + i), scl=max(0.001, vis))
    fx.done(anim, trans=loose)


# ======================================================================
# 3. ICE: the cone in the upper window tips, sprinkles pour out and fall onto the awning
# ======================================================================
def _mm_build_ice():
    fx = _mm_Fx('ice', _mm_up('ice', 4.2, -1.0), face=0.4, big=1.5)
    _mm_D("saucer", (0, 0, -0.62), 0.42, 0.08, _mm_mpm('#7FD6C4'), fx.rig, seg=10)
    cg = _mm_E("cone_pivot", fx.rig, (0, 0, -0.56))
    _mm_D("cone", (0, 0, 0.42), 0.07, 0.84, _mm_mpm('#E3A25A', 0.25, 0.9), cg, seg=8, taper=6.0)
    for c, r, z in (('#FFB8CD', 0.4, 0.98), ('#FFF6E6', 0.34, 1.3), ('#7FD6C4', 0.28, 1.58)):
        _mm_I("scoop", (0, 0, z), r, _mm_mpm(c, 0.4, 0.5), cg, sub=2)
    _mm_I("cherry", (0, 0, 1.86), 0.09, _mm_mpm('#E63946', 0.4), cg)
    sc_cols = ['#FF5C8A', '#FFD166', '#4FC9BE', '#C8B6F2', '#FF9E6B', '#7FB5FF']
    N = 36
    spr = [_mm_B("sprinkle", (0, 0, 0), (0.34, 0.1, 0.1), _mm_mpm(sc_cols[i % 6], 0.5), fx.rig) for i in range(N)]
    rj = _mm_jit(11, N * 6)
    G = 0.024
    spawn = [-3 + 0.25 * (i % 12) for i in range(N)]
    zl = 3.3 - fx.anchor.z                                                    # the awning top (about 3.3 m above the pavement)
    sgn = 1.0 if fx.anchor.x > 0 else -1.0
    land = [(sgn * (-0.5 + 1.4 * rj[i * 6]), 0.55 * rj[i * 6 + 1]) for i in range(N)]   # landing offset (x, y) from the cone: on the awning top (y -1.0 .. -0.45)

    def tilt_of(u):
        if u < -6 or u > 24:
            return 0.0
        if u < 0:
            return -0.13 * _mm_ant(u) + 0.5 * _mm_ss((u + 4) / 4.0)
        return 0.5 * math.exp(-0.17 * u) * math.cos(0.5 * u)

    def anim(self, f, u, u2):
        a = sgn * (tilt_of(u) + tilt_of(u2))
        _mm_K(cg, f, rot=(0, a, 0))
        for i, p in enumerate(spr):
            pos, scl, rot = (0, 0, 0.9), 0.001, (0, 0, 0)
            for hu in (u, u2):
                t = hu - spawn[i]
                if t < 0:
                    continue
                ta = sgn * tilt_of(spawn[i])
                cx0, cz0 = 1.5 * math.sin(ta), -0.56 + 1.55 * math.cos(ta)
                tl = math.sqrt(2 * (cz0 - zl) / G)
                tt = min(t, tl)
                pos = (cx0 + (land[i][0] - cx0) * tt / tl, land[i][1] * tt / tl, max(zl, cz0 - 0.5 * G * tt * tt))
                landed = t >= tl
                rot = (0, 0, rj[i * 6 + 5] * 3) if landed else (rj[i * 6 + 3] * 3 + 0.4 * tt, rj[i * 6 + 4] * 3, rj[i * 6 + 5] * 3 + 0.5 * tt)
                scl = 1.0
                if landed:
                    scl = max(0.001, 1 - _mm_ss((hu - 16) / 6.0))            # they melt away after landing (both rounds)
            _mm_K(p, f, loc=pos, rot=rot, scl=max(0.001, scl))
    fx.done(anim, trans=spr)


# ======================================================================
# 4. CANDY: the jar lid pops, six candies jump
# ======================================================================
def _mm_build_candy():
    fx = _mm_Fx('candy', (1.1, -2.6, 0.15), face=0.6, big=1.08)
    _mm_D("ped", (0, 0, 0.3), 0.5, 0.6, _mm_mpm('#FF9EBB'), fx.rig, seg=10, taper=0.9)
    _mm_D("jar", (0, 0, 1.05), 0.46, 0.9, _mm_blend(M('#EAF4FF', 0.11, alpha=0.5)), fx.rig, seg=10, shadow=False)
    ccols = ['#FF7FA8', '#FFD166', '#4FC9BE', '#C8B6F2', '#FF9E6B', '#7FB5FF']
    rj = _mm_jit(21, 60)
    for i in range(14):
        a = i * 2.399
        rr = 0.3 * math.sqrt((i + 0.5) / 14)
        _mm_I("jar_candy", (math.cos(a) * rr, math.sin(a) * rr, 0.75 + 0.07 * (i % 4)), 0.1, _mm_mpm(ccols[i % 6], 0.4, 0.4), fx.rig)
    lid = _mm_E("lid", fx.rig, (0, 0, 1.54))
    _mm_D("lid_disc", (0, 0, 0), 0.52, 0.1, _mm_mpm('#FF5C8A', 0.3, 0.5), lid, seg=10)
    _mm_I("lid_knob", (0, 0, 0.09), 0.1, _mm_mpm('#FFD166', 0.3, 0.35), lid)
    jump = []
    for i in range(6):
        a = i * TAU / 6 + 0.3
        rest = (math.cos(a) * 0.22, math.sin(a) * 0.22, 1.28)
        jump.append((_mm_I("jumper", rest, 0.14, _mm_mpm(ccols[i], 0.4, 0.4), fx.rig, sub=1), rest, a))
    stars = []
    for i in range(4):
        st = _mm_E("spark", fx.rig, (0, 0, 2.0))
        _mm_P("spark_v", [(0, 0.26), (0.06, 0), (0, -0.26), (-0.06, 0)], 0.03, _mm_mpm('#FFE066', 1.2, 0.35), st)
        _mm_P("spark_h", [(0.26, 0), (0, 0.06), (-0.26, 0), (0, -0.06)], 0.03, _mm_mpm('#FFE066', 1.2, 0.35), st)
        stars.append(st)

    def one(hu):
        """per-action pieces: lid height, spin, jump height factor, spark scale; hu = frame - hit"""
        lid_z = 0.0
        lid_rot = 0.0
        shake = 0.0
        if -6 <= hu < -3:
            shake = 0.05 * math.sin(hu * 4.0) * _mm_ss((hu + 6) / 1.5)
            lid_z = 0.03 * _mm_ss((hu + 6) / 3.0)
        elif -3 <= hu < 0:
            s = (hu + 3) / 3.0
            lid_z = 0.03 + 1.0 * math.sin(s * math.pi / 2)
            lid_rot = TAU * s * 0.9
        elif 0 <= hu <= 9:
            s = hu / 9.0
            lid_z = 1.03 * (1 - s * s)
            lid_rot = TAU * 0.9 + (TAU * 0.1) * s
        elif 9 < hu <= 12:
            lid_z = 0.07 * math.sin((hu - 9) / 3.0 * math.pi)
            lid_rot = TAU
        return lid_z, lid_rot, shake

    def anim(self, f, u, u2):
        lz, lr, sh = 0.0, 0.0, 0.0
        for hu in (u, u2):
            a_, b_, c_ = one(hu)
            lz, lr, sh = lz + a_, lr + b_, sh + c_
        _mm_K(lid, f, loc=(0.0, 0.0, 1.54 + lz), rot=(lr, sh, sh * 0.5))
        for i, (o, rest, a) in enumerate(jump):
            pos = list(rest)
            for hu in (u, u2):
                if -3 <= hu <= 9:
                    H = 0.5 + 0.35 * rj[i]
                    spread = 0.55 + 0.5 * rj[i + 6]
                    if hu < 0:
                        s = (hu + 3) / 3.0
                        h_ = H * math.sin(s * math.pi / 2)
                        k_ = s
                    else:
                        s = hu / 9.0
                        h_ = H * (1 - s * s)
                        k_ = 1 - s * s
                    pos[0] += math.cos(a) * spread * (1 - (1 - k_) ** 2) * 1.0 * (k_ if hu >= 0 else k_)
                    pos[1] += math.sin(a) * spread * 0.5 * k_
                    pos[2] += h_
            _mm_K(o, f, loc=tuple(pos), rot=(u * 0.4 + i, 0, 0))
        for i, st in enumerate(stars):
            a = i * TAU / 4 + 0.7
            r0 = 0.75 + 0.3 * (i % 2)
            sc = max(_mm_pop(u, 3, 8), _mm_pop(u2, 3, 8))
            _mm_K(st, f, loc=(math.cos(a) * r0, -0.1 + 0.0 * i, 2.0 + math.sin(a) * 0.5), scl=max(0.001, sc))
    fx.done(anim, trans=stars)


# ======================================================================
# 5. COOKIE: a cookie board hangs at the upper window facing the street; thin warm wisps of steam rise from it
# ======================================================================
def _mm_build_cookie():
    fx = _mm_Fx('cookie', _mm_up('cookie', -4.2, -0.55), face=0.5, big=1.44)
    wood = _mm_mpm('#C98A5B')
    _mm_B("cb_board", (0, 0.0, -0.05), (1.7, 0.1, 1.25), wood, fx.rig)
    for (cx_, cz_, sx_, sz_) in ((0, 0.6, 1.8, 0.1), (0, -0.7, 1.8, 0.1), (0.85, -0.05, 0.1, 1.3), (-0.85, -0.05, 0.1, 1.3)):
        _mm_B("cb_rim", (cx_, -0.03, cz_), (sx_, 0.14, sz_), _mm_mpm('#FFF6E6'), fx.rig)
    n0 = len(_new)
    for k in range(6):                                     # six big cookies on the face of the board (their tops face the street)
        cx_, cz_ = -0.5 + 0.5 * (k % 3), 0.2 - 0.5 * (k // 3)
        cookie("board_cookie", (cx_, -0.12, cz_), 0.22, 0.08, 'Y', DOUGH if k % 2 == 0 else DOUGH_D, CHIP if k % 2 == 0 else M('#FFF1D8'), nchips=5, seed=k + 3)
    for o in _new[n0:]:
        o.parent = fx.rig
    rj = _mm_jit(31, 60)
    wm = M('#FFE9D4', 1.0, emit='#FFE0C0', strength=0.7)                       # warm cream, flat
    NW = 10
    wisps = [_mm_I("wisp", (0, 0, 0.7), (0.11, 0.07, 0.42), wm, fx.rig, sub=1, shadow=False) for _ in range(NW)]
    life = 22.0

    def anim(self, f, u, u2):
        for i, p in enumerate(wisps):
            t = (u - (-21 + 2.0 * i)) / life
            if 0 < t < 1:
                env = math.sin(math.pi * t) ** 0.7
                sz = max(0.001, env)
                x = (rj[i] - 0.5) * 1.3 + 0.22 * math.sin(t * 4 + i)
                z = 0.7 + 1.2 * t
                _mm_K(p, f, loc=(x, (rj[i + 10] - 0.5) * 0.3 - 0.1, z), rot=(0, 0.35 * math.sin(t * 4 + i), 0), scl=(sz * (0.8 + 0.3 * t), sz, sz * (0.8 + 0.7 * t)))
            else:
                _mm_K(p, f, loc=(0, 0, 0.7), rot=(0, 0, 0), scl=0.001)
    fx.done(anim, trans=wisps)


# ======================================================================
# 6. PET: an aquarium on a wall shelf at the upper window; the fish flick, bubbles grow and pop
# ======================================================================
def _mm_build_pet():
    fx = _mm_Fx('pet', _mm_up('pet', -3.2, -0.55), face=0.5, big=1.4)
    wood = _mm_mpm('#C98A5B')
    _mm_B("tank_shelf", (0, 0, -0.62), (1.7, 0.8, 0.07), wood, fx.rig)
    _mm_B("tank_water", (0, 0, -0.1), (1.4, 0.6, 0.9), _mm_blend(M('#7FD6F0', 0.05, emit='#7FD6F0', strength=0.5, alpha=0.4)), fx.rig, shadow=False)
    for sx in (-0.7, 0.7):
        for sy in (-0.3, 0.3):
            _mm_B("tank_post", (sx, sy, -0.1), (0.05, 0.05, 0.94), _mm_mpm('#FFF6E6'), fx.rig)
    _mm_B("tank_lid", (0, 0, 0.38), (1.5, 0.7, 0.04), _mm_mpm('#FFF6E6'), fx.rig)
    _mm_B("tank_sand", (0, 0, -0.52), (1.4, 0.6, 0.08), _mm_mpm('#FFE0A8'), fx.rig)
    _mm_B("tank_plant", (0.45, 0.15, -0.3), (0.06, 0.06, 0.5), _mm_mpm('#58C27D'), fx.rig)
    _mm_B("tank_plant", (0.55, 0.1, -0.35), (0.06, 0.06, 0.35), _mm_mpm('#9BE5B5'), fx.rig)
    fcols = ['#FF9E6B', '#FFD166', '#FF5C8A', '#FF9E6B']
    fish = []
    for i, c in enumerate(fcols):
        fr = _mm_E("fish", fx.rig)
        _mm_I("fish_body", (0, 0, 0), (0.28, 0.12, 0.18), _mm_mpm(c, 0.4, 0.4), fr)
        tail = _mm_E("fish_tail", fr, (-0.24, 0, 0))
        _mm_P("fish_tailp", [(0.0, 0.0), (-0.24, 0.17), (-0.24, -0.17)], 0.03, _mm_mpm(c, 0.4, 0.4), tail)
        _mm_I("fish_eye", (0.17, -0.1, 0.05), 0.04, _mm_mpm('#FFF6E6', 1.0, 0.4), fr)
        fish.append((fr, tail))
    bub = [_mm_I("bubble", (0, 0, 0.0), 0.11, _mm_blend(M('#EAF8FF', 0.06, emit='#BFEFFF', strength=0.5, alpha=0.6)), fx.rig, sub=1, shadow=False) for _ in range(7)]
    base = [(-0.45, -0.05, 0.1), (-0.1, 0.1, -0.2), (0.25, -0.1, 0.15), (0.5, 0.0, -0.1)]

    def anim(self, f, u, u2):
        for i, (fr, tail) in enumerate(fish):
            bx, by, bz = base[i]
            sw = 0.1 * math.sin(f * 0.22 + i * 1.7)
            d = _mm_act(u)
            flick = _mm_ss((u + 3) / 3.0) * (1 - _mm_ss(u / 8.0)) if -3 < u < 8 else 0.0
            dash = 0.3 * flick * (1 if i % 2 == 0 else -1)
            hop = 0.14 * flick
            yaw = math.pi if i % 2 else 0.0
            heading = yaw + (0.9 * flick * (1 if i % 2 == 0 else -1) if flick > 0 else 0.0)
            tw = 0.35 * math.sin(f * 1.0 + i) * (1 + 3.5 * d)
            _mm_K(fr, f, loc=(bx + sw + dash, by, bz + hop), rot=(0.0, -0.3 * flick, heading))
            _mm_K(tail, f, rot=(0, 0, tw))
        for i, b in enumerate(bub):
            t = (u - (-6 + 1.6 * i)) / 11.0
            if 0 < t < 1:
                x0, y0, z0 = base[i % 4]
                sz = 0.7 + 0.9 * t / 0.88 if t < 0.88 else (1.9 if t < 0.94 else 0.001)     # grows, one frame of pop flash, gone
                _mm_K(b, f, loc=(x0 + 0.1 * math.sin(t * 6 + i), y0, -0.3 + 0.65 * t), scl=max(0.001, sz))
            else:
                _mm_K(b, f, loc=(0, 0, -0.3), scl=0.001)
    fx.done(anim, trans=bub)


# ======================================================================
# 7. COMIC: a POW burst flashes beside the sign
# ======================================================================
def _mm_build_comic():
    fx = _mm_Fx('comic', (5.0, -0.8, 4.4), face=0.8, big=0.88)
    yb = M('#FFD166', 0.4, emit='#FFD166', strength=0.8137)           # unique materials: the emission strength is keyed (the flash)
    pk = M('#FF5C8A', 0.4, emit='#FF5C8A', strength=0.8139)
    wh = M('#FFFFFF', 0.4, emit='#FFFFFF', strength=1.0131)
    bst = _mm_E("burst", fx.rig)
    d0 = disc("burst_y", (0, 0, 0), 0.85, 0.14, yb, seg=14, axis='Y', jit=0.2, seed=4)
    d1 = disc("burst_p", (0, 0, 0), 0.66, 0.12, pk, seg=14, axis='Y', jit=0.18, seed=8)
    _mm_mk(d0, bst, (0, 0.0, 0))
    _mm_mk(d1, bst, (0, -0.09, 0))
    tx = text("POW!", (0, 0, 0), 0.6, wh, extrude=0.06, maxw=1.15)
    _mm_mk(tx, bst, (0, -0.2, 0))
    tx.rotation_euler = (math.pi / 2, 0, 0)
    spikes = []
    for k in range(8):
        a_ = TAU * k / 8 + 0.2
        sp = _mm_E("spike", bst, (math.cos(a_) * 1.0, 0.0, math.sin(a_) * 1.0), (0, math.pi / 2 - a_, 0))
        _mm_P("spike_p", [(-0.15, 0), (0.15, 0), (0, 0.38)], 0.05, yb, sp)
        spikes.append((sp, a_))
    # the spike apex points away from the centre: rotation about Y by pi/2 - a turns +Z to (cos a, sin a) in XZ

    def anim(self, f, u, u2):
        pop = _mm_act(u)
        ant = _mm_ant(u)
        shake = 0.12 * math.sin(f * 1.9) * pop + 0.05 * math.sin(f * 3.0) * ant
        if u < -4:
            pf = 0.001
        elif u < 0:
            pf = max(0.001, _mm_popin((u + 4) / 4.0))            # 4 frames, ends at 1.0 exactly on the hit
        elif u <= 12:
            pf = 1.0
        else:
            pf = max(0.001, 1 - _mm_ss((u - 12) / 6.0))
        _mm_K(bst, f, rot=(0, shake, 0), scl=pf)
        for sp, a_ in spikes:
            r_ = 0.95 + 0.12 * pop - 0.06 * ant
            _mm_K(sp, f, loc=(math.cos(a_) * r_, 0.0, math.sin(a_) * r_), rot=(0, math.pi / 2 - a_, 0))
        for m_, base_ in ((yb, 0.8137), (pk, 0.8139), (wh, 1.0131)):                       # the flash: emission 0.8 -> 5 at the hit
            sk = m_.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
            sk.default_value = base_ + 1.6 * pop ** 2
            sk.keyframe_insert('default_value', frame=f)
    fx.done(anim, trans=[bst])


# ======================================================================
# 8. TRAIN: a toy loco on a rail shelf under the upper window puffs a steam ring
# ======================================================================
def _mm_build_train():
    fx = _mm_Fx('train', _mm_up('train', 2.6, -0.55), face=0.4, big=1.0)
    zb = -0.55
    _mm_B("rail_beam", (0, 0, zb - 0.06), (2.2, 0.34, 0.1), _mm_mpm('#E3A25A'), fx.rig)
    for yy in (-0.11, 0.11):
        _mm_B("rail", (0, yy, zb + 0.015), (2.2, 0.04, 0.04), _mm_mpm('#DDE3EA'), fx.rig)
    for xx in (-0.85, 0.85):
        _mm_B("rail_brace", (xx, 0.2, zb - 0.3), (0.08, 0.4, 0.5), _mm_mpm('#7A9E9F'), fx.rig)
    loco, wheels = _mm_loco(fx.rig, 1.5, body='#F25C54')
    loco.location = (0.0, 0.0, zb + 0.035)
    ring = _mm_torus("steam_ring", 0.5, 0.13, SMK, fx.rig)
    ring2 = _mm_torus("steam_ring2", 0.34, 0.1, SMK, fx.rig)
    puffs = [_mm_I("steam", (0, 0, 0), 0.2, SMK, fx.rig, sub=1, shadow=False) for _ in range(4)]
    cx0, cz0 = 0.36, zb + 0.035 + 0.93

    def anim(self, f, u, u2):
        fwd = 0.35 * _mm_act(u) * (1 - _mm_act(u)) * 2 - 0.12 * _mm_ant(u)
        _mm_K(loco, f, loc=(fwd, 0.0, zb + 0.035 + 0.04 * _mm_act(u)))
        for w in wheels:
            _mm_K(w, f, rot=(0, -fwd / 0.14, 0))
        for r_, off, s0 in ((ring, 0, 1.0), (ring2, 5, 0.8)):
            t = (u - (-9 + off)) / 21.0
            if 0 < t < 1:
                grow = 0.6 + 1.7 * math.sin(math.pi * min(1.0, t * 1.25) / 2) * s0
                vis = math.sin(math.pi * t) ** 0.5
                _mm_K(r_, f, loc=(cx0 + 0.5 * t, 0.0, cz0 + 0.3 + 1.3 * t), rot=(math.pi / 2, 0, 0), scl=max(0.001, grow * vis * 1.1))
            else:
                _mm_K(r_, f, loc=(0, 0, cz0), rot=(math.pi / 2, 0, 0), scl=0.001)
        for i, p in enumerate(puffs):
            t = (u - (-12 + 3 * i)) / 14.0
            if 0 < t < 1:
                _mm_K(p, f, loc=(cx0 + 0.1 * i + 0.25 * t, 0.0, cz0 + 0.1 + 1.0 * t), scl=max(0.001, 1.5 * math.sin(math.pi * t) ** 0.7 * (0.8 + 0.4 * t)))
            else:
                _mm_K(p, f, loc=(cx0, 0, cz0), scl=0.001)
    fx.done(anim, trans=[ring, ring2] + puffs)


# ======================================================================
# 9. BIKE: the wall emblem bike: its front wheel spins and a gold bell on the handlebar rings (the emblem is a base object; two pivots are added to it)
# ======================================================================
def _mm_build_bike():
    S_ = _mm_shop('bike')
    fx = _mm_Fx('bike', (0, 0, 0.0))                       # placeholder rig (no parts); the action parts hang on the emblem rig so they follow its sway
    erig = S_['emb'][0]
    M0 = shop_matrix(S_['cx'], S_['side'])
    wparts = [o for o in _mm_desc(erig) if o.type == 'MESH' and o.name.startswith(('wheel_tire', 'wheel_rim', 'spoke'))]
    front = []
    for o in wparts:
        cx_ = sum(Vector(c).x for c in o.bound_box) / 8
        if cx_ > 0.3:
            front.append(o)
    tire = next(o for o in front if o.name.startswith('wheel_tire'))
    cen = sum((Vector(c) for c in tire.bound_box), Vector()) / 8            # wheel centre in the emblem frame (local shop axes)
    pinv = front[0].matrix_parent_inverse.copy()
    wp = bpy.data.objects.new("mom_bike_wheel", None)
    scene.collection.objects.link(wp)
    wp.parent = erig
    wp.matrix_parent_inverse = pinv
    wp.matrix_basis = M0 @ Matrix.Translation(cen)
    for o in front:
        o.parent = wp
        o.matrix_parent_inverse = (M0 @ Matrix.Translation(cen)).inverted()
    bp = bpy.data.objects.new("mom_bike_bell", None)
    scene.collection.objects.link(bp)
    bp.parent = erig
    bp.matrix_parent_inverse = pinv
    bp.matrix_basis = M0 @ Matrix.Translation((0.68, -0.85, 1.12)) @ Matrix.Scale(1.8, 4)
    gold = _mm_mpm('#FFD166', 0.3, 0.6)
    bell = _mm_E("bell", bp)
    _mm_I("bell_dome", (0, 0, 0.1), (0.3, 0.3, 0.26), gold, bell, sub=2)
    _mm_B("bell_base", (0, 0, 0.0), (0.24, 0.24, 0.06), _mm_mpm('#FFF6E6'), bell)
    marks = []
    for ang in (-1.0, -0.35, 0.35, 1.0):
        m_ = _mm_E("bell_mark", bp, (0.0, 0.0, 0.12))
        _mm_B("mark", (math.sin(ang) * 0.6, 0, math.cos(ang) * 0.6), (0.09, 0.05, 0.3), _mm_mpm('#FFD166', 0.5, 0.45), m_, rot=(0, -ang, 0))
        marks.append(m_)
    rig_ = fx.rig

    def anim(self, f, u, u2):
        sp = _mm_bellS(u, TAU * 2.0) + _mm_bellS(u2, TAU * 2.0)
        _mm_K(wp, f, rot=(0, -sp, 0))
        sw = 0.0
        for hu in (u, u2):
            if hu >= 0:
                sw += 0.6 * math.exp(-0.28 * hu) * math.cos(1.6 * hu)
            elif hu > -6:
                sw += -0.15 * _mm_ant(hu)
        _mm_K(bell, f, rot=(0, sw, 0))
        for m_ in marks:
            sc = max(_mm_pop(u, 3, 9), _mm_pop(u2, 3, 9)) * (1.0 + 0.1 * math.sin(f * 2.5))
            _mm_K(m_, f, rot=(0, 0, 0), scl=max(0.001, sc))
    fx.run(anim, trans=marks)


# ======================================================================
# 10. ARCADE: a screen on the facade flashes colours on the beat, pixel sparks pop out, a coin blips
# ======================================================================
def _mm_build_arcade():
    fx = _mm_Fx('arcade', _mm_up('arcade', -3.2, -0.55), face=0.4, big=1.5)
    body, trim = _mm_mpm('#8E7CC3'), _mm_mpm('#FF5C8A')
    _mm_B("scr_body", (0, 0.0, 0), (1.7, 0.2, 1.5), body, fx.rig)
    _mm_B("scr_top", (0, -0.02, 0.85), (1.8, 0.26, 0.2), trim, fx.rig)
    _mm_B("scr_bot", (0, -0.02, -0.85), (1.8, 0.26, 0.2), trim, fx.rig)
    sm = M('#7DF9FF', 0.3, emit='#7DF9FF', strength=1.2371)                 # unique material: its colour and emission are keyed
    _mm_B("scr_screen", (0, -0.12, 0.0), (1.4, 0.04, 1.2), sm, fx.rig, shadow=False)
    pat = ["0010100", "0111110", "1101011", "1111111", "1010101"]                  # a little invader on the screen (flat boxes, not black)
    for r_, row in enumerate(pat):
        for c_, ch in enumerate(row):
            if ch == '1':
                _mm_B("pix", ((c_ - 3) * 0.15, -0.16, (2 - r_) * 0.15), (0.13, 0.03, 0.13), _mm_mpm('#5C4E7A', 0.2), fx.rig, shadow=False)
    for k, c in enumerate(('#7DF9FF', '#FFE066', '#B6FF5C')):
        _mm_D("btn", (-0.4 + 0.4 * k, -0.2, -0.85), 0.07, 0.04, _mm_mpm(c), fx.rig, seg=8, axis='Y')
    cols = [srgb('#FF5CD9'), srgb('#FFE066'), srgb('#7DF9FF'), srgb('#B6FF5C')]       # the hit frame shows pink
    pc = ['#7DF9FF', '#FF5CD9', '#FFE066', '#B6FF5C', '#FF9E6B', '#C8B6F2', '#7DF9FF', '#FF5CD9']
    pix = [_mm_B("pixel", (0, -0.3, 0), (0.2, 0.2, 0.2), _mm_mpm(pc[i], 1.0, 0.4), fx.rig) for i in range(8)]
    coin = _mm_D("coin", (0.0, -0.3, -1.0), 0.2, 0.05, _mm_mpm('#FFD166', 0.3, 0.5), fx.rig, seg=10, axis='Y')
    rj = _mm_jit(41, 20)

    def flash(hu):
        """Colour changes at most every 6 frames (a half beat): idle cyan, yellow build-up, PINK on the hit, green, back to cyan."""
        if hu < -6:
            return 1.2, 2
        if hu < 0:
            return 1.2 + 0.9 * _mm_ss((hu + 6) / 6.0), 1
        if hu < 6:
            return 2.8 - 0.8 * _mm_ss(hu / 6.0), 0
        if hu < 12:
            return 2.0 - 0.6 * _mm_ss((hu - 6) / 6.0), 3
        if hu < 18:
            return 1.4 - 0.2 * _mm_ss((hu - 12) / 6.0), 2
        return 1.2, 2

    def anim(self, f, u, u2):
        st, ci = flash(u2 if u2 > -6 else u)
        col = cols[ci]
        sk = sm.node_tree.nodes["Principled BSDF"].inputs
        for nm, val in (("Emission Color", (*col, 1)), ("Base Color", (*col, 1)), ("Emission Strength", st)):
            sk[nm].default_value = val
            sk[nm].keyframe_insert('default_value', frame=f)
        for i, p in enumerate(pix):
            sc, pos = 0.0, (0, -0.3, 0)
            for hu in (u, u2):
                e = _mm_pop(hu, 3, 11)
                if e > 0:
                    a = i * TAU / 8 + 0.4
                    rr = 1.0 + 0.5 * rj[i] + 0.35 * (1 - e) * (1 if hu >= 0 else 0)             # flies out after the hit
                    pos = (math.cos(a) * rr, -0.3 - 0.2 * e, math.sin(a) * rr * 0.9)
                    sc = max(sc, e)
            _mm_K(p, f, loc=pos, rot=(0.4 * u, 0.5 * u, 0), scl=max(0.001, sc))
        cz, cs = -1.0, 0.0
        for hu in (u, u2):
            if -5 <= hu <= 5:
                cz = -1.0 + 1.3 * math.sin((hu + 5) / 10.0 * math.pi)             # the coin is highest exactly on the hit
                cs = max(cs, _mm_pop(hu, 4, 5))
        _mm_K(coin, f, loc=(0.0, -0.3, cz), rot=(0, 0, f * 0.6), scl=max(0.001, cs))
    fx.done(anim, trans=pix + [coin])


for _fn in (_mm_build_toy, _mm_build_book, _mm_build_ice, _mm_build_candy, _mm_build_cookie, _mm_build_pet, _mm_build_comic, _mm_build_train, _mm_build_bike, _mm_build_arcade):
    _fn()
bpy.context.preferences.edit.keyframe_new_interpolation_type = 'BEZIER'
at(Matrix.Identity(4))
print("FX moments: %d moments" % len(MOM_RIGS))
