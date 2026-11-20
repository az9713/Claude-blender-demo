"""V2: the motion follows the music's beat (see make_walk_music.py -> walk_beats.json). Output: walk2.blend, walk2_frames/, walk2.png.
Kevin Cookie Company neighbourhood, WALK version: a Saturday-morning stroll down the street, no zoom, nobody goes inside.
Same low-poly pastel style as build_cookie_shop.py (the hero shop is rebuilt from the same geometry).
Run: blender.exe -b -P build_neighborhood_walk.py -- still [frame] [percent]   -> walk.png
     blender.exe -b -P build_neighborhood_walk.py -- anim [first last]    -> walk_frames/f_NNNN.png
Z up, metres. The street runs along X. North row (y > 0) faces -Y. South row faces +Y.
Road centre line y = -9. Sidewalk fronts: north y = 0, south y = -18."""
import bpy, bmesh, json, math, os, random, sys
from mathutils import Matrix, Vector, Euler

OUT = os.path.dirname(os.path.abspath(__file__))
# PUNCH scales every beat-locked motion: 1 = the first v2 look (very subtle), 2.5 = default. TAG names the outputs (v2 used walk2).
PUNCH = float(os.environ.get('WALK_PUNCH', '2.5'))
PB, PF = min(PUNCH, 2.0), min(PUNCH, 1.6)      # capped: walker hop (PB) and flag / emblem swing (PF) look wrong when too large
TAG = os.environ.get('WALK_TAG', 'walk3')
# ---- the music's beat grid: one beat = 12.5 frames. Footfalls, sways and sign glow all follow it, so the street seems to move with the tune.
BEAT = 12.5
try:
    BEATS = json.load(open(os.path.join(OUT, 'walk_beats.json')))
    BEAT0 = BEATS['beat0'] % BEAT
except OSError:
    BEATS, BEAT0 = None, 8.5     # no beat file: old behaviour for the signs, same beat grid for the rest

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
MODE = ARGS[0] if ARGS else 'still'
STILL_FRAME = int(ARGS[1]) if len(ARGS) > 1 else 60
PERCENT = int(ARGS[2]) if (len(ARGS) > 2 and MODE == 'still') else 100
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
TAU = math.tau
YS = -18.0   # world y of the south row's sidewalk-side front line


# ---------- helpers ----------
def srgb(h):
    h = h.lstrip('#')
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b))


def shade(h, f):
    h = h.lstrip('#')
    c = [max(0, min(255, int(int(h[i:i + 2], 16) * f))) for i in (0, 2, 4)]
    return '#%02X%02X%02X' % tuple(c)


_mats = {}
def M(hexcol, rough=0.85, emit=None, strength=0.0, alpha=1.0, bump=None, brick=None):
    key = (hexcol, rough, emit, strength, alpha, bump, brick)
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new("m_" + hexcol.lstrip('#') + ("_e" if emit else "") + ("_a" if alpha < 1 else ""))
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*srgb(hexcol), 1)
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*srgb(emit), 1)
        b.inputs["Emission Strength"].default_value = strength
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
    if bump or brick:
        tc = nt.nodes.new('ShaderNodeTexCoord')
        bp = nt.nodes.new('ShaderNodeBump')
        if brick:
            scale, hex2, mortar = brick
            mp = nt.nodes.new('ShaderNodeMapping')
            mp.inputs['Rotation'].default_value = (math.pi / 2, 0, 0)
            nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
            br = nt.nodes.new('ShaderNodeTexBrick')
            br.inputs['Color1'].default_value = (*srgb(hexcol), 1)
            br.inputs['Color2'].default_value = (*srgb(hex2), 1)
            br.inputs['Mortar'].default_value = (*srgb(mortar), 1)
            br.inputs['Scale'].default_value = scale
            br.inputs['Mortar Size'].default_value = 0.03
            nt.links.new(mp.outputs['Vector'], br.inputs['Vector'])
            nt.links.new(br.outputs['Color'], b.inputs['Base Color'])
            nt.links.new(br.outputs['Fac'], bp.inputs['Height'])
            bp.inputs['Strength'].default_value = 0.6
        else:
            scale, st = bump
            n = nt.nodes.new('ShaderNodeTexNoise')
            n.inputs['Scale'].default_value = scale
            n.inputs['Detail'].default_value = 6
            nt.links.new(tc.outputs['Object'], n.inputs['Vector'])
            nt.links.new(n.outputs['Fac'], bp.inputs['Height'])
            bp.inputs['Strength'].default_value = st
        bp.inputs['Distance'].default_value = 0.05
        nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    _mats[key] = m
    return m


# CUR is the matrix of the frame we build in. Shops are built in a local frame (front at y=0, facing -Y)
# and CUR moves that frame to its place in the street (the south row is turned 180 degrees).
CUR = Matrix.Identity(4)
_new = []


def at(m):
    global CUR
    CUR = m


def shop_matrix(cx, side):
    if side == 'N':
        return Matrix.Translation((cx, 0, 0))
    return Matrix.Translation((cx, YS, 0)) @ Matrix.Rotation(math.pi, 4, 'Z')


def place(o, loc=(0, 0, 0), rot=None):
    m = CUR @ Matrix.Translation(loc)
    if rot is not None:
        m = m @ Euler(rot).to_matrix().to_4x4()
    o.matrix_world = m
    _new.append(o)


def build(name, bm, m=None, loc=(0, 0, 0), shadow=True):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = False
    if m:
        me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    place(o, loc)
    if not shadow:
        o.visible_shadow = False
    return o


def box(name, x0, x1, y0, y1, z0, z1, m, rot=None, shadow=True):
    bm = bmesh.new()
    pts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
           (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    vs = [bm.verts.new(p) for p in pts]
    for f in ([0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]):
        bm.faces.new([vs[i] for i in f])
    if rot is not None:
        bmesh.ops.transform(bm, matrix=rot, verts=bm.verts)
    return build(name, bm, m, shadow=shadow)


def disc(name, c, r, h, m, seg=10, axis='Z', jit=0.0, seed=0, taper=1.0):
    rnd = random.Random(seed)
    bm = bmesh.new()
    r0, r1 = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        rr = r * (1 + rnd.uniform(-jit, jit))
        for w, ring, k in ((-h / 2, r0, 1.0), (h / 2, r1, taper)):
            u, v = math.cos(a) * rr * k, math.sin(a) * rr * k
            p = (c[0] + u, c[1] + v, c[2] + w) if axis == 'Z' else (c[0] + u, c[1] + w, c[2] + v)
            ring.append(bm.verts.new(p))
    bm.faces.new(r0)
    bm.faces.new(r1)
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new([r0[i], r0[j], r1[j], r1[i]])
    return build(name, bm, m)


def pulse_bulb(o, i):
    """Driver: the bulb swells and shrinks once per beat; the three bulb groups are a third of a beat apart, so a ripple runs along the string."""
    for ax in range(3):
        d = o.driver_add('scale', ax).driver
        d.type = 'SCRIPTED'
        d.expression = "1+%.3f*cos((frame-%.3f)/%.3f*6.2832-%.4f)" % (0.07 * PUNCH, BEAT0, BEAT, i * TAU / 3)
    return o


def ico(name, c, s, m, sub=1, shadow=True):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
    sx, sy, sz = (s, s, s) if isinstance(s, (int, float)) else s
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    return build(name, bm, m, loc=c, shadow=shadow)


def tri_prism(name, pts, t, m, y0=0.0, shadow=True):
    """Prism from a polygon in the XZ plane, thickness t along +Y starting at y0."""
    bm = bmesh.new()
    f1 = [bm.verts.new((p[0], y0, p[1])) for p in pts]
    f2 = [bm.verts.new((p[0], y0 + t, p[1])) for p in pts]
    bm.faces.new(f1)
    bm.faces.new(f2[::-1])
    for k in range(len(pts)):
        j = (k + 1) % len(pts)
        bm.faces.new([f1[k], f1[j], f2[j], f2[k]])
    return build(name, bm, m, shadow=shadow)


def rod(name, p0, p1, r, m, shadow=False):
    a, b = Vector(p0), Vector(p1)
    d = b - a
    rot = Matrix.Translation((a + b) / 2) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    return box(name, -r, r, -r, r, -d.length / 2, d.length / 2, m, rot=rot, shadow=shadow)


def frame(x0, x1, z0, z1, m, t=0.15, y0=-0.12, y1=0.4):
    box("fr_l", x0 - t, x0, y0, y1, z0 - t, z1 + t, m)
    box("fr_r", x1, x1 + t, y0, y1, z0 - t, z1 + t, m)
    box("fr_b", x0 - t, x1 + t, y0 - 0.06, y1, z0 - t, z0, m)
    box("fr_t", x0 - t, x1 + t, y0, y1, z1, z1 + t, m)


def empty(name, loc=(0, 0, 0), rot=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    scene.collection.objects.link(e)
    place(e, loc, rot)
    return e


def adopt(objs, rig):
    bpy.context.view_layer.update()
    inv = rig.matrix_world.inverted()
    for o in objs:
        o.parent = rig
        o.matrix_parent_inverse = inv


def child(o, parent, loc=None):
    o.parent = parent
    if loc is not None:
        o.location = loc
    return o


def pbox(name, x0, x1, y0, y1, z0, z1, m, pv, parent):
    o = box(name, x0 - pv[0], x1 - pv[0], y0 - pv[1], y1 - pv[1], z0 - pv[2], z1 - pv[2], m)
    o.location = pv
    o.parent = parent
    return o


def to_track(o, target):
    d = Vector(target) - o.location
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


FONT = None
for fp in (r"C:\Windows\Fonts\comicbd.ttf", r"C:\Windows\Fonts\ARLRDBD.TTF", r"C:\Windows\Fonts\arialbd.ttf"):
    if os.path.exists(fp):
        FONT = bpy.data.fonts.load(fp)
        break


def text(body, loc, size, m, rot=(math.pi / 2, 0, 0), extrude=0.04, maxw=None):
    cu = bpy.data.curves.new("t_" + body[:10], 'FONT')
    cu.body = body
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.size = size
    cu.extrude = extrude
    if FONT:
        cu.font = FONT
    cu.materials.append(m)
    o = bpy.data.objects.new("txt_" + body[:10], cu)
    scene.collection.objects.link(o)
    place(o, loc, rot)
    if maxw:
        bpy.context.view_layer.update()
        if o.dimensions.x > maxw:
            s = maxw / o.dimensions.x
            o.scale = (s, s, s)
    return o


def cookie(name, c, r, h, axis, dough, chip, nchips=8, seed=1, sprinkles=False):
    disc(name, c, r, h, dough, seg=12, axis=axis, jit=0.04, seed=seed)
    ang0 = seed * 1.3
    for k in range(nchips):
        a = k * 2.399 + ang0
        rad = r * 0.72 * math.sqrt((k + 0.5) / nchips)
        u, v = math.cos(a) * rad, math.sin(a) * rad
        sz = r * (0.13 if not sprinkles else 0.07) * (0.85 + 0.3 * ((k * 7) % 5) / 4)
        if axis == 'Y':
            pos, s = (c[0] + u, c[1] - h / 2, c[2] + v), (sz, sz * 0.55, sz)
        else:
            pos, s = (c[0] + u, c[1] + v, c[2] + h / 2), (sz, sz, sz * 0.55)
        ico(name + "_chip", pos, s, chip)


def cupcake(c, wrap, frost, cherry=True):
    disc("cc_wrap", (c[0], c[1], c[2] + 0.08), 0.12, 0.16, wrap, seg=8, taper=1.35)
    ico("cc_frost", (c[0], c[1], c[2] + 0.21), (0.16, 0.16, 0.12), frost)
    if cherry:
        ico("cc_cherry", (c[0], c[1], c[2] + 0.33), 0.045, M('#E63946'))


# ---------- palette ----------
CREAM = M('#FFF1D8')
CHOC = M('#4A2A1C', 0.7)
CHOC2 = M('#2B2B33', 0.7)
DOUGH = M('#E3A25A', 0.9, bump=(14, 0.7))
DOUGH_D = M('#6B3E26', 0.9)
CHIP = M('#4B2A1E', 0.8)
FROST = M('#FF8FB5', 0.7)
GOLD = M('#FFD166', 0.35)
WHITE = M('#FFFFFF', 0.6)
GLASS = M('#FFD9A0', 0.05, emit='#FFB45C', strength=1.0, alpha=0.30)
GLASS_DARK = M('#1B2450', 0.1, alpha=0.6)
GLOW_GLASS = M('#FFE2A8', 0.3, emit='#FFC76B', strength=2.0)
WARM_BULB = M('#FFE7B0', 0.4, emit='#FFC070', strength=14)
POLE = M('#3D5A6C', 0.7)
SIDEWALK_G = M('#C6BBC9', 0.95)
TILE_VAR = [M('#EFE6EE', 0.95, bump=(30, 0.3)), M('#E6DCE8', 0.95, bump=(30, 0.3)), M('#F3EAF0', 0.95, bump=(30, 0.3))]
LEAF = M('#58C27D')
PASTELS = ['#FF7FA8', '#FFD166', '#4FC9BE', '#C8B6F2', '#FF9E6B', '#7FB5FF', '#9BE5B5']

# ======================================================================
# Kind-specific things: window items, wall emblem, outside props
# ======================================================================
def table(x0, x1, col):
    box("disp_table", x0, x1, 0.55, 1.75, 0.19, 0.72, M(col))
    box("disp_top", x0 - 0.05, x1 + 0.05, 0.5, 1.8, 0.72, 0.78, CREAM)


def bear(c, col, s=1.0, belly='#FFF1D8'):
    x, y, z = c
    f = M(col, 0.9)
    ico("bear_body", (x, y, z + 0.22 * s), (0.2 * s, 0.17 * s, 0.24 * s), f)
    ico("bear_belly", (x, y - 0.1 * s, z + 0.2 * s), (0.12 * s, 0.06 * s, 0.15 * s), M(belly))
    ico("bear_head", (x, y - 0.02 * s, z + 0.55 * s), 0.16 * s, f)
    ico("bear_snout", (x, y - 0.15 * s, z + 0.5 * s), 0.06 * s, M(belly))
    ico("bear_nose", (x, y - 0.2 * s, z + 0.52 * s), 0.02 * s, CHOC2)
    for sx in (-1, 1):
        ico("bear_ear", (x + sx * 0.13 * s, y, z + 0.7 * s), 0.06 * s, f)
        ico("bear_eye", (x + sx * 0.06 * s, y - 0.14 * s, z + 0.58 * s), 0.02 * s, CHOC2)
        ico("bear_arm", (x + sx * 0.22 * s, y - 0.02 * s, z + 0.3 * s), (0.06 * s, 0.06 * s, 0.14 * s), f)
        ico("bear_leg", (x + sx * 0.12 * s, y - 0.1 * s, z + 0.06 * s), 0.08 * s, f)


def wheel(c, r, tire, rim, spokes=6, thick=0.06):
    disc("wheel_tire", c, r, thick, tire, seg=12, axis='Y')
    disc("wheel_rim", (c[0], c[1] - thick * 0.4, c[2]), r * 0.78, thick * 0.9, rim, seg=12, axis='Y')
    for k in range(spokes):
        a = math.pi * k / spokes
        rot = Matrix.Translation(c) @ Matrix.Rotation(a, 4, 'Y')
        box("spoke", -0.012, 0.012, -thick * 0.5 - 0.02, -thick * 0.5 - 0.005, -r * 0.8, r * 0.8, tire, rot=rot, shadow=False)


def bike(c, col, s=1.0):
    x, y, z = c
    r = 0.36 * s
    fr = M(col, 0.5)
    wheel((x - 0.5 * s, y, z + r), r, CHOC2, M('#DDE3EA'), 5, 0.05)
    wheel((x + 0.5 * s, y, z + r), r, CHOC2, M('#DDE3EA'), 5, 0.05)
    a, b_, cc, d_ = (x - 0.5 * s, y, z + r), (x + 0.5 * s, y, z + r), (x - 0.05 * s, y, z + r + 0.4 * s), (x + 0.38 * s, y, z + r + 0.42 * s)
    seat = (x - 0.18 * s, y, z + r + 0.55 * s)
    bb = (x, y, z + r * 0.9)
    for p, q in ((a, seat), (seat, bb), (bb, a), (seat, d_), (bb, d_), (d_, b_), (d_, (x + 0.34 * s, y, z + r + 0.62 * s))):
        rod("bike_frame", p, q, 0.012, fr)
    box("bike_seat", x - 0.3 * s, x - 0.08 * s, y - 0.05, y + 0.05, z + r + 0.55 * s, z + r + 0.6 * s, CHOC2)
    box("bike_bar", x + 0.3 * s, x + 0.38 * s, y - 0.2 * s, y + 0.2 * s, z + r + 0.6 * s, z + r + 0.64 * s, CHOC2)


def lolly(c, r, cols, stick=0.7, axis_y=True):
    x, y, z = c
    for k, col in enumerate(cols):
        disc("lolly", (x, y - 0.015 * k, z), r * (1 - 0.2 * k), 0.04, M(col, 0.4), seg=10, axis='Y')
    if stick > 0:
        box("lolly_stick", x - 0.012, x + 0.012, y - 0.01, y + 0.01, z - stick, z - r * 0.5, WHITE)


def cone(c, scoops, s=1.0):
    x, y, z = c
    disc("cone", (x, y, z + 0.18 * s), 0.03 * s, 0.36 * s, M('#E3A25A', 0.9, bump=(40, 0.6)), seg=8, taper=6.0)
    for k, col in enumerate(scoops):
        ico("scoop", (x, y, z + (0.42 + 0.24 * k) * s), 0.17 * s, M(col, 0.5))
    ico("cherry", (x, y, z + (0.42 + 0.24 * (len(scoops) - 1) + 0.19) * s), 0.04 * s, M('#E63946'))


def puppy(c, col, s=1.0, ear='#7A4B2A'):
    x, y, z = c
    f = M(col, 0.9)
    ico("pup_body", (x, y, z + 0.17 * s), (0.2 * s, 0.13 * s, 0.14 * s), f)
    ico("pup_head", (x, y - 0.2 * s, z + 0.3 * s), 0.11 * s, f)
    ico("pup_snout", (x, y - 0.3 * s, z + 0.27 * s), (0.06 * s, 0.05 * s, 0.045 * s), M('#F6D6A8'))
    ico("pup_nose", (x, y - 0.35 * s, z + 0.28 * s), 0.02 * s, CHOC2)
    for sx in (-1, 1):
        ico("pup_ear", (x + sx * 0.1 * s, y - 0.18 * s, z + 0.32 * s), (0.04 * s, 0.05 * s, 0.09 * s), M(ear, 0.9))
        ico("pup_eye", (x + sx * 0.045 * s, y - 0.29 * s, z + 0.33 * s), 0.017 * s, CHOC2)
        for sy in (-1, 1):
            box("pup_leg", x + sx * 0.12 * s - 0.03 * s, x + sx * 0.12 * s + 0.03 * s, y + sy * 0.08 * s - 0.03 * s,
                y + sy * 0.08 * s + 0.03 * s, z, z + 0.1 * s, f)
    ico("pup_tail", (x, y + 0.2 * s, z + 0.22 * s), (0.025 * s, 0.07 * s, 0.025 * s), f)


def kitten(c, col, s=1.0):
    x, y, z = c
    f = M(col, 0.9)
    ico("kit_body", (x, y, z + 0.14 * s), (0.12 * s, 0.17 * s, 0.13 * s), f)
    ico("kit_head", (x, y - 0.16 * s, z + 0.27 * s), 0.1 * s, f)
    for sx in (-1, 1):
        box("kit_ear", x + sx * 0.06 * s - 0.02 * s, x + sx * 0.06 * s + 0.02 * s, y - 0.17 * s, y - 0.15 * s, z + 0.33 * s, z + 0.43 * s, f)
        ico("kit_eye", (x + sx * 0.04 * s, y - 0.25 * s, z + 0.29 * s), 0.015 * s, M('#9BE5B5', 0.3, emit='#9BE5B5', strength=2))
    box("kit_tail", x - 0.015 * s, x + 0.015 * s, y + 0.15 * s, y + 0.38 * s, z + 0.14 * s, z + 0.18 * s, f)


def book(x, y, z, w, h, d, col):
    box("book", x, x + w, y, y + d, z, z + h, M(col, 0.7))
    box("book_pages", x + 0.01, x + w - 0.01, y - 0.004, y + 0.0, z + 0.02, z + h - 0.02, CREAM)


def crate(x, y, w, d, h, col='#C98A5B'):
    box("crate", x - w / 2, x + w / 2, y - d / 2, y + d / 2, 0.15, 0.15 + h, M(col, 0.9))
    box("crate_band", x - w / 2 - 0.01, x + w / 2 + 0.01, y - d / 2 - 0.01, y + d / 2 + 0.01, 0.15 + h * 0.45, 0.15 + h * 0.6, M('#A8714A', 0.9))


def screen_cab(x, y, col, scr, h=1.7, w=0.8, front=-1):
    box("cab", x - w / 2, x + w / 2, y - 0.4, y + 0.4, 0.19, 0.19 + h * 0.62, M(col, 0.6))
    box("cab_top", x - w / 2, x + w / 2, y - 0.3, y + 0.4, 0.19 + h * 0.62, 0.19 + h, M(col, 0.6))
    box("cab_screen", x - w * 0.38, x + w * 0.38, y - 0.31, y - 0.29, 0.19 + h * 0.66, 0.19 + h * 0.94, M(scr, 0.3, emit=scr, strength=4))
    box("cab_panel", x - w * 0.42, x + w * 0.42, y - 0.5, y - 0.38, 0.19 + h * 0.5, 0.19 + h * 0.58, M('#2B2B5C', 0.6))
    ico("cab_ball", (x - 0.12, y - 0.48, 0.19 + h * 0.62), 0.05, M('#FF5C8A', 0.4))
    ico("cab_btn", (x + 0.12, y - 0.5, 0.19 + h * 0.6), 0.04, M('#FFD166', 0.4))


# window items: functions (x, k) drawn on a display table (z=0.78) at y=1.2
def it_blocks(x, k):
    cols = ['#FF7FA8', '#FFD166', '#4FC9BE', '#C8B6F2']
    for r, n in enumerate((3, 2, 1)):
        for j in range(n):
            bx = x + (j - (n - 1) / 2) * 0.34
            box("blk", bx - 0.15, bx + 0.15, 1.05, 1.35, 0.78 + r * 0.3, 1.08 + r * 0.3, M(cols[(r + j + k) % 4]))


def it_bear(x, k):
    bear((x, 1.2, 0.78), ['#C98A4B', '#F2C6A0', '#E8707F', '#9BA8D6'][k % 4], 1.3)


def it_balls(x, k):
    for j, col in enumerate(('#FF5C8A', '#FFD166', '#4FC9BE', '#7FB5FF')):
        ico("ball", (x + (j % 2 - 0.5) * 0.35, 1.1 + (j // 2) * 0.35, 0.95), 0.17, M(col, 0.4))


def it_horse(x, k):
    f = M('#C98A4B', 0.8)
    box("rocker", x - 0.45, x + 0.45, 1.1, 1.14, 0.78, 0.84, M('#7A4B2A'))
    box("rocker", x - 0.45, x + 0.45, 1.3, 1.34, 0.78, 0.84, M('#7A4B2A'))
    box("horse_body", x - 0.3, x + 0.3, 1.12, 1.32, 1.0, 1.3, f)
    box("horse_neck", x + 0.18, x + 0.34, 1.14, 1.3, 1.25, 1.65, f)
    ico("horse_head", (x + 0.43, 1.22, 1.62), (0.14, 0.09, 0.09), f)
    box("horse_mane", x + 0.1, x + 0.2, 1.2, 1.24, 1.3, 1.68, M('#FF7FA8'))
    for sx in (-0.22, 0.22):
        box("horse_leg", x + sx - 0.04, x + sx + 0.04, 1.14, 1.3, 0.84, 1.02, f)


def it_robot(x, k):
    box("robot_body", x - 0.2, x + 0.2, 1.05, 1.35, 0.95, 1.4, M('#7FB5FF', 0.4))
    box("robot_head", x - 0.15, x + 0.15, 1.08, 1.32, 1.4, 1.65, M('#C8D6E8', 0.4))
    for sx in (-1, 1):
        ico("robot_eye", (x + sx * 0.06, 1.07, 1.55), 0.03, M('#FFD166', 0.3, emit='#FFD166', strength=3))
        box("robot_leg", x + sx * 0.1 - 0.05, x + sx * 0.1 + 0.05, 1.1, 1.3, 0.78, 0.95, M('#5C7CC9'))
        box("robot_arm", x + sx * 0.28 - 0.04, x + sx * 0.28 + 0.04, 1.12, 1.28, 1.05, 1.35, M('#5C7CC9'))
    box("robot_ant", x - 0.01, x + 0.01, 1.19, 1.21, 1.65, 1.8, M('#FF5C8A'))


def it_jar(x, k):
    cols = ['#FF5C8A', '#FFD166', '#4FC9BE', '#C8B6F2', '#FF9E6B']
    disc("cjar", (x, 1.2, 1.0), 0.3, 0.44, M('#EAF4FF', 0.1, alpha=0.5), seg=8)
    for j in range(9):
        a = j * 2.399
        ico("candy", (x + math.cos(a) * 0.17 * (j % 3) / 2, 1.2 + math.sin(a) * 0.17 * (j % 3) / 2, 0.88 + 0.07 * (j // 2)), 0.07, M(cols[(j + k) % 5], 0.4))
    disc("cjar_lid", (x, 1.2, 1.26), 0.2, 0.08, M('#FF5C8A'), seg=8)


def it_lollistand(x, k):
    disc("lstand", (x, 1.2, 0.82), 0.3, 0.08, M('#FF5C8A'), seg=10)
    cols = [('#FF5C8A', '#FFFFFF'), ('#4FC9BE', '#FFFFFF'), ('#FFD166', '#FF9E6B'), ('#C8B6F2', '#FFFFFF')]
    for j in range(5):
        a = j * TAU / 5
        lolly((x + math.cos(a) * 0.2, 1.2 + math.sin(a) * 0.12, 1.35 + 0.08 * (j % 2)), 0.17, list(cols[j % 4]), stick=0.5)


def it_gumball(x, k):
    box("gb_base", x - 0.2, x + 0.2, 1.0, 1.4, 0.78, 1.0, M('#FF5C8A'))
    ico("gb_globe", (x, 1.2, 1.35), 0.32, M('#CFEFFF', 0.1, alpha=0.4))
    for j in range(8):
        a = j * 2.399
        ico("gb_ball", (x + math.cos(a) * 0.16, 1.2 + math.sin(a) * 0.16, 1.2 + 0.07 * j), 0.07, M(PASTELS[j % 7], 0.4))


def it_cane(x, k):
    for j in range(4):
        px = x + (j - 1.5) * 0.18
        for q in range(5):
            rod("cane", (px, 1.2, 0.82 + q * 0.13), (px, 1.2, 0.82 + (q + 1) * 0.13), 0.03, M('#FF3D5C' if q % 2 == 0 else '#FFFFFF', 0.5), True)
        rod("cane", (px, 1.2, 1.47), (px + 0.09, 1.2, 1.57), 0.03, M('#FF3D5C'), True)


def it_books_up(x, k):
    cols = ['#E63946', '#2A6F97', '#F4A261', '#2A9D8F', '#9B5DE5', '#FFD166']
    z = 0.78
    for j in range(5):
        h = 0.5 + 0.18 * ((j * 3 + k) % 3)
        book(x - 0.5 + j * 0.2, 1.1, z, 0.17, h, 0.4, cols[(j + k) % 6])


def it_books_flat(x, k):
    cols = ['#FF7FA8', '#4FC9BE', '#FFD166', '#7FB5FF', '#C8B6F2']
    for j in range(4):
        box("book_flat", x - 0.4 + 0.02 * (j % 2), x + 0.4 + 0.02 * (j % 2), 1.0, 1.45, 0.78 + j * 0.09, 0.86 + j * 0.09, M(cols[(j + k) % 5], 0.7))
    bear((x + 0.05, 1.2, 0.78 + 0.36), '#F2C6A0', 0.8)


def it_globe(x, k):
    disc("globe_stand", (x, 1.2, 0.82), 0.16, 0.08, M('#7A4B2A'), seg=8)
    ico("globe", (x, 1.2, 1.1), 0.28, M('#4FC9BE', 0.5), sub=2)
    ico("globe_land", (x + 0.05, 1.12, 1.18), (0.14, 0.1, 0.12), M('#9BE5B5', 0.8))


def it_sundae(x, k):
    disc("glass_stem", (x, 1.2, 0.88), 0.04, 0.18, WHITE, seg=6)
    disc("glass_bowl", (x, 1.2, 1.06), 0.22, 0.2, M('#EAF4FF', 0.1, alpha=0.5), seg=8, taper=1.5)
    for j, col in enumerate((('#FFB8CD', '#FFF6E6', '#7A4B2A'))):
        ico("scoop", (x + (j - 1) * 0.16, 1.2, 1.28), 0.14, M(col, 0.5))
    ico("cherry", (x, 1.2, 1.46), 0.045, M('#E63946'))


def it_cones(x, k):
    cone((x - 0.25, 1.2, 0.78), ['#FFB8CD', '#FFF6E6'], 1.0)
    cone((x + 0.25, 1.2, 0.78), ['#7A4B2A', '#9BE5B5', '#FFD166'], 0.9)


def it_pen(x, k):
    for sx in (-0.55, 0.55):
        box("pen_post", x + sx - 0.02, x + sx + 0.02, 0.95, 1.0, 0.78, 1.25, M('#FFFFFF'))
    box("pen_rail", x - 0.55, x + 0.55, 0.95, 1.0, 1.1, 1.15, M('#FFFFFF'))
    puppy((x - 0.15, 1.3, 0.78), ['#E3A25A', '#F6D6A8', '#8D5B3A'][k % 3], 1.3)
    kitten((x + 0.3, 1.4, 0.78), ['#F2994A', '#C8C8D8'][k % 2], 1.1)


def it_fish(x, k):
    box("tank_base", x - 0.5, x + 0.5, 0.95, 1.45, 0.78, 0.86, M('#7A4B2A'))
    box("tank", x - 0.48, x + 0.48, 0.97, 1.43, 0.86, 1.4, M('#9BE5F5', 0.05, emit='#6FD3F0', strength=0.5, alpha=0.35))
    for j in range(4):
        ico("fish", (x - 0.3 + j * 0.2, 1.2, 1.0 + 0.1 * (j % 3)), (0.07, 0.04, 0.05), M(['#FF9E6B', '#FFD166', '#FF5C8A', '#FFD166'][j], 0.4))
    box("tank_plant", x + 0.3, x + 0.34, 1.2, 1.24, 0.86, 1.15, M('#58C27D'))


def it_train(x, k):
    for j in range(7):
        box("sleeper", x - 0.6 + j * 0.2, x - 0.5 + j * 0.2, 0.95, 1.45, 0.78, 0.8, M('#7A4B2A'))
    for yy in (1.08, 1.32):
        box("rail", x - 0.62, x + 0.7, yy, yy + 0.025, 0.8, 0.83, M('#B8C0CC', 0.3))
    box("loco_body", x - 0.5, x + 0.0, 1.1, 1.3, 0.86, 1.08, M('#E63946', 0.5))
    box("loco_cab", x - 0.5, x - 0.3, 1.08, 1.32, 1.08, 1.3, M('#2B2B5C'))
    disc("loco_chim", (x + 0.1, 1.2, 1.12), 0.04, 0.14, CHOC2, seg=6)
    box("loco_boiler", x - 0.3, x + 0.18, 1.12, 1.28, 0.95, 1.14, M('#E63946', 0.5))
    box("car1", x + 0.25, x + 0.62, 1.12, 1.28, 0.86, 1.04, M('#4FC9BE', 0.5))
    for wx in (-0.4, -0.1, 0.35, 0.55):
        for yy in (1.09, 1.31):
            disc("tw", (x + wx, yy, 0.88), 0.045, 0.02, CHOC2, seg=6, axis='Y')


def it_kits(x, k):
    for j in range(3):
        box("kit", x - 0.4 + j * 0.28, x - 0.14 + j * 0.28, 1.05, 1.3, 0.78, 1.15 + 0.1 * j, M(['#7FB5FF', '#FFD166', '#FF7FA8'][j], 0.7))
    box("plane_body", x - 0.35, x + 0.35, 1.2, 1.32, 1.45, 1.55, M('#FFFFFF', 0.5))
    box("plane_wing", x - 0.08, x + 0.08, 1.0, 1.52, 1.47, 1.5, M('#E63946', 0.5))


def it_helmet(x, k):
    ico("helmet", (x, 1.2, 1.0), (0.24, 0.28, 0.2), M(PASTELS[k % 7], 0.4))
    box("helmet_strap", x - 0.12, x + 0.12, 1.12, 1.28, 0.8, 0.84, CHOC2)
    box("deck", x - 0.7, x - 0.3, 1.0, 1.3, 0.8, 0.84, M('#FF5C8A'))


def it_bike_win(x, k):
    bike((x, 1.3, 0.78), PASTELS[(k + 1) % 7], 0.9)


def it_game(x, k):
    for j in range(4):
        box("gbox", x - 0.45 + j * 0.24, x - 0.25 + j * 0.24, 1.05 + 0.03 * j, 1.1 + 0.03 * j, 0.8, 1.15, M(PASTELS[(j + k) % 7], 0.5))
    box("console", x - 0.3, x + 0.3, 1.2, 1.5, 0.78, 0.9, M('#2B2B5C'))
    box("tv", x - 0.34, x + 0.34, 1.5, 1.6, 0.9, 1.45, M('#1B1B3A'))
    box("tv_screen", x - 0.3, x + 0.3, 1.47, 1.5, 0.94, 1.41, M('#7DF9FF', 0.3, emit='#7DF9FF', strength=3))


def it_comicrack(x, k):
    disc("rack_pole", (x, 1.2, 1.1), 0.03, 0.7, CHOC2, seg=6)
    for j in range(6):
        a = j * TAU / 6
        rot = Matrix.Translation((x + math.cos(a) * 0.22, 1.2 + math.sin(a) * 0.22, 1.2)) @ Matrix.Rotation(a + math.pi / 2, 4, 'Z')
        box("comic", -0.12, 0.12, -0.01, 0.01, -0.2, 0.2, M(PASTELS[(j + k) % 7], 0.5), rot=rot)


def it_cabinet(x, k):
    screen_cab(x, 1.15, ['#2B2B5C', '#5C2B5C', '#2B5C5C'][k % 3], ['#7DF9FF', '#FF5CD9', '#B6FF5C'][k % 3], h=1.8, w=0.8)


def it_claw(x, k):
    box("claw_base", x - 0.45, x + 0.45, 0.75, 1.55, 0.19, 0.75, M('#FF5C8A'))
    box("claw_box", x - 0.45, x + 0.45, 0.75, 1.55, 0.75, 1.75, M('#BFEFFF', 0.05, emit='#7DF9FF', strength=0.6, alpha=0.35))
    for j in range(6):
        a = j * 2.399
        ico("plush", (x + math.cos(a) * 0.25, 1.15 + math.sin(a) * 0.25, 0.9 + 0.06 * (j % 2)), 0.13, M(PASTELS[j % 7], 0.9))


ITEMS = {
    'cookie': ('#A6E3CF', None),   # handled by hero_display
    'toy': ('#7FB5FF', [it_blocks, it_bear, it_horse, it_balls, it_robot]),
    'candy': ('#FF9EBB', [it_jar, it_lollistand, it_gumball, it_cane]),
    'train': ('#7A9E9F', [it_train, it_kits]),
    'bike': ('#FFD166', [it_bike_win, it_helmet, it_bike_win]),
    'book': ('#C98A5B', [it_books_up, it_globe, it_books_flat]),
    'ice': ('#7FD6C4', [it_sundae, it_cones]),
    'pet': ('#E8D8A8', [it_pen, it_fish, it_pen]),
    'comic': ('#5C4E7A', [it_game, it_comicrack]),
    'arcade': ('#2B2B5C', [it_cabinet, it_claw, it_cabinet]),
}


def hero_display(i, x0, x1):
    table(x0, x1, '#A6E3CF')
    xm = (x0 + x1) / 2
    if i == 0:
        for k, (dx, dough, chip) in enumerate(((-0.8, DOUGH, CHIP), (0.0, DOUGH_D, M('#FFF1D8')), (0.8, M('#FFA3C0'), M('#FFFFFF')))):
            for t in range(3):
                cookie("stack", (xm + dx + 0.03 * ((t * 3) % 2), 1.2, 0.84 + t * 0.09), 0.3, 0.08, 'Z',
                       dough, chip, nchips=5, seed=k * 5 + t, sprinkles=(k == 2))
    else:
        for (zp, r) in ((0.95, 0.85), (1.55, 0.6), (2.05, 0.38)):
            disc("tier", (xm, 1.2, zp), r, 0.05, WHITE, seg=12)
        for (zp0, zp1) in ((0.78, 0.95), (0.95, 1.55), (1.55, 2.05)):
            disc("pole", (xm, 1.2, (zp0 + zp1) / 2), 0.04, zp1 - zp0, GOLD, seg=6)
        for k in range(6):
            a = k * math.pi / 3
            cupcake((xm + math.cos(a) * 0.55, 1.2 + math.sin(a) * 0.55, 0.975), [M('#4FC9BE'), M('#FFD166'), M('#C8B6F2')][k % 3],
                    [FROST, WHITE, M('#FFD7A8')][k % 3])
        for k in range(3):
            a = k * TAU / 3 + 0.5
            cupcake((xm + math.cos(a) * 0.32, 1.2 + math.sin(a) * 0.32, 1.575), M('#FF7FA8'), WHITE)
        cookie("tower_top", (xm, 1.2, 2.2), 0.24, 0.08, 'Z', DOUGH, CHIP, nchips=5, seed=11)


def display(kind, i, x0, x1):
    if kind == 'cookie':
        hero_display(i, x0, x1)
        return
    tcol, items = ITEMS[kind]
    table(x0, x1, tcol)
    n = max(1, int((x1 - x0) // 1.5))
    for k in range(n):
        x = x0 + (x1 - x0) * (k + 0.5) / n
        items[(k + i) % len(items)](x, k + i)


def hanging(kind, x0, x1, H):
    """Things that hang from the ceiling inside the window."""
    n = max(1, int((x1 - x0) // 2.2))
    for k in range(n):
        x = x0 + (x1 - x0) * (k + 0.5) / n
        if kind == 'toy':
            rot = Matrix.Translation((x, 1.0, 2.15)) @ Matrix.Rotation(math.pi / 4, 4, 'Y')
            box("kite", -0.22, 0.22, -0.01, 0.01, -0.22, 0.22, M(PASTELS[k % 7], 0.6), rot=rot)
            box("kite_str", x - 0.005, x + 0.005, 0.99, 1.01, 2.4, 3.2, CREAM)
        elif kind == 'train':
            box("hplane", x - 0.3, x + 0.3, 1.0, 1.12, 2.1, 2.2, M('#FFFFFF', 0.5))
            box("hplane_w", x - 0.07, x + 0.07, 0.8, 1.32, 2.13, 2.16, M('#4FC9BE', 0.5))
            box("hplane_s", x - 0.005, x + 0.005, 1.04, 1.06, 2.2, 3.2, CREAM)
        elif kind == 'candy':
            lolly((x, 1.0, 2.3), 0.2, ['#FF5C8A', '#FFFFFF', '#FF5C8A'], stick=0.0)
            box("hl_str", x - 0.005, x + 0.005, 0.99, 1.01, 2.45, 3.2, CREAM)
        elif kind in ('comic', 'arcade'):
            c = '#FF5CD9' if k % 2 == 0 else '#7DF9FF'
            box("neon", x - 0.5, x + 0.5, 0.6, 0.64, 2.35, 2.4, M(c, 0.3, emit=c, strength=5))
        elif kind in ('ice', 'book', 'pet', 'bike'):
            disc("pend", (x, 1.0, 2.3), 0.14, 0.1, M('#FFF6E6', 0.4, emit='#FFC070', strength=1.2), seg=8, taper=1.6)
            box("pend_cord", x - 0.005, x + 0.005, 0.99, 1.01, 2.35, 3.2, CHOC)


# ---------- wall emblem: the big sculpture above the sign (the hero has the giant cookie) ----------
def emblem(kind, zc):
    """Returns the animation mode: 'roll' spins in the wall plane, 'sway' swings, 'pulse' scales."""
    y = -0.3
    if kind == 'cookie':
        CK = (0.0, y, 0.0)
        disc("giant_cookie", CK, 0.98, 0.42, DOUGH, seg=12, axis='Y', jit=0.04, seed=5)
        disc("giant_crown", (0, y - 0.2, 0), 0.8, 0.05, M('#EDB46E', 0.9), seg=12, axis='Y', jit=0.05, seed=9)
        for k in range(11):
            a = k * 2.399 + 0.7
            rad = 0.72 * math.sqrt((k + 0.5) / 11)
            sz = 0.13 * (0.85 + 0.3 * ((k * 7) % 5) / 4)
            ico("giant_chip", (math.cos(a) * rad, y - 0.25, math.sin(a) * rad), (sz, sz * 0.55, sz), CHIP)
        rnd = random.Random(42)
        for k in range(16):
            a = rnd.uniform(0, TAU); rad = 0.78 * math.sqrt(rnd.random()); sz = rnd.uniform(0.035, 0.07)
            ico("giant_crumb", (math.cos(a) * rad, y - 0.24, math.sin(a) * rad), (sz, sz * 0.5, sz), M('#6B3E26', 0.8))
        for k in range(30):
            a = rnd.uniform(0, TAU); rad = 0.8 * math.sqrt(rnd.random())
            ico("giant_sugar", (math.cos(a) * rad, y - 0.235, math.sin(a) * rad), (0.018, 0.01, 0.018), M('#FFFFFF', 0.4, emit='#FFFFFF', strength=0.4))
        for k in range(12):
            a = TAU * k / 12 + 0.2
            ico("giant_rim", (math.cos(a) * 0.93, y - 0.12, math.sin(a) * 0.93), (0.11, 0.2, 0.11), M('#C98A4B', 0.9))
        return 'roll'
    if kind == 'toy':
        bear((0, y - 0.1, -0.85), '#C98A4B', 3.4)
        box("bowtie", -0.25, 0.25, y - 0.62, y - 0.56, -0.36, -0.2, M('#E63946'))
        return 'sway'
    if kind == 'candy':
        lolly((0, y - 0.1, 0.35), 0.95, ['#FF5C8A', '#FFFFFF', '#FF5C8A', '#FFFFFF', '#FF5C8A'], stick=0.0)
        return 'roll'
    if kind == 'train':
        wheel((0, y - 0.1, 0), 0.95, M('#2B2B5C', 0.5), M('#E63946', 0.5), 8, 0.2)
        ico("wheel_hub", (0, y - 0.35, 0), 0.16, GOLD)
        rod("rodlink", (0, y - 0.4, 0.0), (0.5, y - 0.4, 0.6), 0.05, GOLD, True)
        return 'roll'
    if kind == 'bike':
        bike((0, y - 0.1, -0.95), '#FF5C8A', 2.0)
        return 'sway'
    if kind == 'book':
        for sx in (-1, 1):
            rot = Matrix.Translation((sx * 0.62, y - 0.1, 0)) @ Matrix.Rotation(-sx * 0.28, 4, 'Y')
            box("bk_cover", -0.62, 0.62, -0.05, 0.05, -0.8, 0.8, M('#E63946' if sx < 0 else '#2A6F97', 0.7), rot=rot)
            rot2 = Matrix.Translation((sx * 0.62, y - 0.17, 0)) @ Matrix.Rotation(-sx * 0.28, 4, 'Y')
            box("bk_pages", -0.58, 0.58, -0.04, 0.04, -0.74, 0.74, CREAM, rot=rot2)
        return 'sway'
    if kind == 'ice':
        cone((0, y - 0.1, -0.95), ['#FFB8CD', '#FFF6E6', '#7FD6C4'], 2.6)
        return 'sway'
    if kind == 'pet':
        mat = M('#FFF1D8', 0.8)
        box("bone", -0.7, 0.7, y - 0.2, y - 0.05, -0.12, 0.12, mat)
        for sx in (-0.7, 0.7):
            for sz in (-0.14, 0.14):
                ico("bone_knob", (sx, y - 0.12, sz), 0.17, mat)
        return 'sway'
    if kind == 'comic':
        disc("burst", (0, y - 0.1, 0), 1.0, 0.1, M('#FFD166', 0.5), seg=14, axis='Y', jit=0.22, seed=4)
        disc("burst2", (0, y - 0.18, 0), 0.8, 0.06, M('#FF5C8A', 0.5), seg=14, axis='Y', jit=0.2, seed=8)
        text("POW!", (0, y - 0.26, 0), 0.62, M('#FFFFFF', 0.4, emit='#FFFFFF', strength=1.2), extrude=0.05, maxw=1.4)
        return 'pulse'
    if kind == 'arcade':
        pat = ["00100000100", "00010001000", "00111111100", "01101110110", "11111111111", "10111111101", "10100000101", "00011011000"]
        mg = M('#7DF9FF', 0.3, emit='#7DF9FF', strength=5)
        for r_, row in enumerate(pat):
            for c_, ch in enumerate(row):
                if ch == '1':
                    box("pix", (c_ - 5.5) * 0.17, (c_ - 4.5) * 0.17, y - 0.2, y - 0.04, (3.5 - r_) * 0.17 - 0.08, (4.5 - r_) * 0.17 - 0.08, mg, shadow=False)
        return 'pulse'
    return 'sway'


# ---------- outside props ----------
def outside(S):
    kind, dx = S['kind'], S['door_x']
    # flower pots by the door
    for sx in (dx - 1.25, dx + 1.25):
        disc("pot", (sx, -0.45, 0.4), 0.22, 0.5, M('#E07A5F'), seg=8, taper=1.25)
        for k, col in enumerate(('#FF7FA8', '#FFD166', '#FFFFFF', '#FF7FA8')):
            ico("pot_flower", (sx + (k - 1.5) * 0.1, -0.45 + (0.06 if k % 2 else -0.06), 0.78 + 0.05 * (k % 2)), 0.1, M(col, 0.6))
        ico("pot_leaf", (sx, -0.45, 0.68), (0.22, 0.22, 0.12), LEAF)
    # chalkboard A-frame
    cx = dx - 2.3 if dx >= 0 else dx + 2.3
    for sgn, yb in ((-1, -1.5), (1, -1.2)):
        rot = Matrix.Translation((cx, yb, 0.15)) @ Matrix.Rotation(sgn * math.radians(10), 4, 'X')
        box("chalk_panel", -0.32, 0.32, -0.025, 0.025, 0.0, 0.9, M('#2F3B45', 0.9) if sgn < 0 else CHOC, rot=rot)
    box("chalk_top", cx - 0.35, cx + 0.35, -1.42, -1.28, 1.0, 1.04, CHOC)
    text(S['chalk'], (cx, -1.43, 0.72), 0.14, M('#FFF6E6', 0.6, emit='#FFF6E6', strength=0.5), rot=(math.pi / 2 - 0.1745, 0, 0), extrude=0.004, maxw=0.6)
    # kind props
    if kind in ('cookie', 'ice'):
        for tx, top in ((dx - 3.6, '#FF9EBB'), (dx + 3.6, '#FFD166')):
            if abs(tx) > 4.6:
                continue
            disc("table_base", (tx, -2.4, 0.17), 0.28, 0.04, POLE, seg=10)
            disc("table_pole", (tx, -2.4, 0.55), 0.05, 0.76, POLE, seg=6)
            disc("table_top", (tx, -2.4, 0.94), 0.56, 0.06, M(top, 0.6), seg=12)
            for phi in (math.radians(200), math.radians(340)):
                px, py = tx + 0.9 * math.cos(phi), -2.4 + 0.9 * math.sin(phi)
                R = Matrix.Translation((px, py, 0)) @ Matrix.Rotation(phi + math.pi / 2, 4, 'Z')
                sm = M('#4FC9BE' if tx < dx else '#C8B6F2', 0.7)
                for lx in (-0.17, 0.17):
                    for ly in (-0.17, 0.17):
                        box("chair_leg", lx - 0.02, lx + 0.02, ly - 0.02, ly + 0.02, 0.15, 0.6, POLE, rot=R)
                box("chair_seat", -0.21, 0.21, -0.21, 0.21, 0.6, 0.66, sm, rot=R)
                box("chair_back", -0.21, 0.21, -0.23, -0.19, 0.66, 1.15, sm, rot=R)
            disc("plate", (tx - 0.15, -2.5, 0.98), 0.19, 0.02, WHITE, seg=10)
            if kind == 'cookie':
                cookie("table_cookie", (tx - 0.15, -2.5, 1.02), 0.14, 0.05, 'Z', DOUGH, CHIP, nchips=3, seed=4)
            else:
                cone((tx - 0.15, -2.5, 0.98), ['#FFB8CD'], 0.5)
            disc("lantern", (tx + 0.3, -2.6, 1.0), 0.05, 0.1, WARM_BULB, seg=6)
    elif kind == 'toy':
        crate(dx + 3.4, -1.0, 1.2, 0.8, 0.5, '#7FB5FF')
        for j in range(4):
            ico("toy_ball", (dx + 3.1 + j * 0.28, -1.0 + 0.1 * (j % 2), 0.82), 0.14, M(PASTELS[j % 7], 0.4))
        bear((dx + 3.55, -1.0, 0.65), '#C98A4B', 1.1)
    elif kind == 'candy':
        crate(dx + 3.4, -1.0, 1.2, 0.8, 0.5, '#FF9EBB')
        for j in range(4):
            lolly((dx + 3.0 + j * 0.28, -1.0, 1.1), 0.15, [PASTELS[j % 7], '#FFFFFF'], stick=0.5)
    elif kind == 'train':
        crate(dx - 3.3, -1.0, 1.2, 0.8, 0.5, '#7A9E9F')
        for j in range(3):
            box("kitbox", dx - 3.7 + j * 0.4, dx - 3.4 + j * 0.4, -1.1, -0.85, 0.65, 0.9, M(PASTELS[(j + 2) % 7], 0.6))
    elif kind == 'bike':
        for j in range(3):
            bike((dx + 3.0 - j * 0.75, -1.9, 0.15), PASTELS[(j * 2) % 7], 1.0)
        box("rack_bar", dx + 0.7, dx + 3.4, -2.3, -2.26, 0.15, 0.2, POLE)
    elif kind == 'book':
        box("cart_body", dx - 3.4, dx - 2.2, -1.5, -0.8, 0.5, 0.9, M('#7A4B2A'))
        for j in range(7):
            book(dx - 3.35 + j * 0.16, -1.3, 0.9, 0.13, 0.4 + 0.08 * (j % 3), 0.35, ['#E63946', '#2A6F97', '#F4A261', '#2A9D8F', '#9B5DE5'][j % 5])
        for sx in (-3.3, -2.3):
            disc("cart_wheel", (dx + sx, -1.5, 0.33), 0.18, 0.04, CHOC2, seg=8, axis='Y')
    elif kind == 'pet':
        box("kennel", dx + 2.7, dx + 3.9, -1.6, -0.7, 0.15, 0.85, M('#C98A5B'))
        tri_prism("kennel_roof", [(dx + 2.6, 0.85), (dx + 4.0, 0.85), (dx + 3.3, 1.35)], 0.95, M('#B7594A'), y0=-1.65)
        puppy((dx + 3.3, -1.75, 0.15), '#E3A25A', 1.4)
        disc("bowl", (dx + 2.2, -1.5, 0.19), 0.15, 0.08, M('#FF5C8A'), seg=8)
    elif kind in ('comic', 'arcade'):
        c = '#FF5CD9' if kind == 'arcade' else '#FFD166'
        box("mat_neon", dx - 1.2, dx + 1.2, -1.3, -1.25, 0.15, 0.19, M(c, 0.3, emit=c, strength=2))


# ======================================================================
# The shop builder (local frame: front wall at y=0..0.4, interior +Y, sidewalk -Y)
# ======================================================================
BULB_M = [M('#FFE7B0', 0.4, emit='#FFC070', strength=3 + i * 0.01) for i in range(3)]
FLAG_COL = ['#FF7FA8', '#FFD166', '#4FC9BE', '#C8B6F2', '#FF9E6B']
SHOPS_BUILT = []   # keeps animation handles
FLAGS = []
SIGN_MATS = []


def shop(S):
    at(shop_matrix(S['cx'], S['side']))
    kind, H, dx, hw = S['kind'], S['H'], S['door_x'], 5.0
    wall = M(S['wall'], 0.9, bump=(45, 0.25))
    base = M(S['base'], 0.85, brick=(6.0, shade(S['base'], 0.93), '#E9F7F0'))
    acc = M(S['acc'])
    floor = M(S['floor'])
    # ---- shell
    box("floor_slab", -hw, hw, 0, 6, 0, 0.15, floor)
    box("wall_l", -hw, -hw + 0.4, 0.4, 6, 0.15, H, wall)
    box("wall_r", hw - 0.4, hw, 0.4, 6, 0.15, H, wall)
    box("wall_b", -hw, hw, 5.6, 6, 0.15, H, wall)
    box("upper_block", -hw, hw, 0.4, 6, 3.4, H, wall)
    wins = []
    if (dx - 1.6) - (-hw + 0.4) > 1.4:
        wins.append((-hw + 0.4, dx - 1.6))
    if (hw - 0.4) - (dx + 1.6) > 1.4:
        wins.append((dx + 1.6, hw - 0.4))
    openings = sorted([(a, b, 2.7) for a, b in wins] + [(dx - 0.9, dx + 0.9, 2.4)])
    xs = -hw
    for (x0, x1, zt) in openings:
        if x0 > xs + 1e-3:
            box("pillar", xs, x0, 0, 0.4, 0.8, H, wall)
        box("header", x0, x1, 0, 0.4, zt, H, wall)
        xs = x1
    if hw > xs + 1e-3:
        box("pillar", xs, hw, 0, 0.4, 0.8, H, wall)
    box("base_L", -hw, dx - 0.9, -0.05, 0.4, 0, 0.8, base)
    box("base_R", dx + 0.9, hw, -0.05, 0.4, 0, 0.8, base)
    box("base_cap_L", -hw - 0.05, dx - 0.9, -0.12, 0.0, 0.7, 0.8, CREAM)
    box("base_cap_R", dx + 0.9, hw + 0.05, -0.12, 0.0, 0.7, 0.8, CREAM)
    # ---- roof line
    box("cornice", -hw - 0.3, hw + 0.3, -0.35, 6.3, H, H + 0.4, acc)
    box("cornice_band", -hw - 0.12, hw + 0.12, -0.14, 0.0, H - 0.3, H, CREAM)
    roof = S['roof']
    if roof == 'flat':
        for i in range(-9, 10):
            box("tooth", i * 0.55 - 0.18, i * 0.55 + 0.18, -0.42, -0.35, H + 0.1, H + 0.3, CREAM)
    elif roof == 'stepped':
        box("step_blk", -3.2, 3.2, -0.1, 0.5, H + 0.4, H + 1.3, wall)
        box("step_cap", -3.45, 3.45, -0.3, 0.7, H + 1.3, H + 1.6, acc)
        box("step_band", -3.2, 3.2, -0.3, -0.1, H + 0.55, H + 0.75, CREAM)
        for i in range(-4, 5):
            box("tooth", i * 0.55 - 0.18, i * 0.55 + 0.18, -0.42, -0.35, H + 0.1, H + 0.3, CREAM)
    elif roof == 'gable':
        tri_prism("gable", [(-hw - 0.1, H + 0.4), (hw + 0.1, H + 0.4), (0, H + 2.5)], 0.5, wall)
        for sx in (-1, 1):
            rod("gable_trim", (sx * (hw + 0.2), -0.2, H + 0.4), (0, -0.2, H + 2.6), 0.09, acc, True)
        box("gable_vent", -0.3, 0.3, -0.05, 0.0, H + 0.9, H + 1.5, M(shade(S['wall'], 0.8)))
    # ---- upper lit windows with flower boxes
    zu0 = H - 2.4
    tints = ['#FFE2A8', '#FFD0A0', '#FFE9B8']
    for j, (x0, x1) in enumerate(((-4.25, -2.95), (2.95, 4.25))):
        frame(x0, x1, zu0, zu0 + 1.4, CREAM, t=0.12)
        box("up_glass", x0, x1, -0.04, 0.0, zu0, zu0 + 1.4, M(tints[(j + S['cx'] // 10) % 3 if isinstance(S['cx'], int) else j], 0.3, emit='#FFC76B', strength=2.0))
        xm = (x0 + x1) / 2
        box("up_mull_v", xm - 0.03, xm + 0.03, -0.02, 0.12, zu0, zu0 + 1.4, CREAM)
        box("up_mull_h", x0, x1, -0.02, 0.12, zu0 + 0.67, zu0 + 0.73, CREAM)
        box("up_planter", x0 - 0.15, x1 + 0.15, -0.5, 0.0, zu0 - 0.25, zu0, M(shade(S['acc'], 1.0)))
        for k in range(4):
            ico("up_flower", (x0 + 0.15 + k * (x1 - x0 - 0.3) / 3, -0.25, zu0 + 0.1), 0.13, M(PASTELS[(k + j) % 7], 0.6))
    # ---- windows (display glass + items)
    for i, (x0, x1) in enumerate(wins):
        frame(x0, x1, 0.8, 2.7, CREAM)
        box("glass", x0, x1, 0.18, 0.24, 0.8, 2.7, GLASS, shadow=False)
        nm = max(1, round((x1 - x0) / 2.6))
        for k in range(1, nm):
            xm = x0 + (x1 - x0) * k / nm
            box("mullion_v", xm - 0.04, xm + 0.04, -0.02, 0.28, 0.8, 2.7, CREAM)
        box("mullion_h", x0, x1, -0.02, 0.28, 1.75, 1.83, CREAM)
        for (a, b, c, d) in ((x0 + 0.2, x1 - 0.2, 0.2, 0.26), (x0 + 0.2, x1 - 0.2, 0.6, 0.66)):
            box("panel_h", a, b, -0.1, -0.05, c, d, CREAM)
        display(kind, i, x0 + 0.1, x1 - 0.1)
        hanging(kind, x0 + 0.1, x1 - 0.1, H)
    # ---- door (leaf group gets a hinge)
    frame(dx - 0.9, dx + 0.9, 0.15, 2.4, CREAM)
    box("doormat", dx - 0.8, dx + 0.8, -0.95, -0.12, 0.15, 0.19, M('#E8707F'))
    box("step", dx - 1.05, dx + 1.05, -0.3, 0.0, 0.0, 0.3, CREAM)
    leaf0 = len(_new)
    dm = M(S['doorc'], 0.75)
    box("door_low", dx - 0.85, dx + 0.85, 0.08, 0.22, 0.15, 1.0, dm)
    box("door_stile_L", dx - 0.85, dx - 0.6, 0.08, 0.22, 1.0, 2.35, dm)
    box("door_stile_R", dx + 0.6, dx + 0.85, 0.08, 0.22, 1.0, 2.35, dm)
    box("door_rail", dx - 0.85, dx + 0.85, 0.08, 0.22, 2.1, 2.35, dm)
    box("door_glass", dx - 0.6, dx + 0.6, 0.13, 0.17, 1.0, 2.1, GLASS, shadow=False)
    ico("door_knob", (dx + 0.72, 0.03, 1.05), 0.065, GOLD)
    leaf = _new[leaf0:]
    hinge = empty("hinge_" + kind, (dx - 0.85, 0.15, 0.0))
    adopt(leaf, hinge)
    # ---- awning
    n = round((2 * hw + 0.5) / 1.05)
    xl, xr = -hw - 0.25, hw + 0.25
    w = (xr - xl) / n
    phi, L = math.atan2(0.6, 1.3), math.hypot(1.3, 0.6)
    sa, sb = M(S['awnA'], 0.8, bump=(220, 0.12)), M(S['awnB'], 0.8, bump=(220, 0.12))
    for i in range(n):
        xa, xb = xl + i * w, xl + (i + 1) * w
        m = sa if i % 2 == 0 else sb
        rot = Matrix.Translation((0, -0.65, 3.3)) @ Matrix.Rotation(phi, 4, 'X')
        box("awning_stripe", xa, xb, -L / 2, L / 2, -0.03, 0.03, m, rot=rot)
        bm = bmesh.new()
        tri = [(xa, -1.3, 3.0), (xb, -1.3, 3.0), ((xa + xb) / 2, -1.3, 2.62)]
        f1 = [bm.verts.new(p) for p in tri]
        f2 = [bm.verts.new((p[0], p[1] + 0.06, p[2])) for p in tri]
        bm.faces.new(f1)
        bm.faces.new(f2[::-1])
        for k in range(3):
            j = (k + 1) % 3
            bm.faces.new([f1[k], f1[j], f2[j], f2[k]])
        build("awning_valance", bm, m)
    for sx in (xl, xr):
        bm = bmesh.new()
        p = [(sx, 0.0, 3.6), (sx, -1.3, 3.0), (sx, 0.0, 3.0)]
        a = [bm.verts.new(q) for q in p]
        b = [bm.verts.new((q[0] + 0.05 * (1 if sx > 0 else -1), q[1], q[2])) for q in p]
        bm.faces.new(a)
        bm.faces.new(b[::-1])
        for k in range(3):
            j = (k + 1) % 3
            bm.faces.new([a[k], a[j], b[j], b[k]])
        build("awning_cheek", bm, sb)
    box("awning_piping", xl, xr, -1.34, -1.28, 2.97, 3.05, M('#FFF6E6', 0.6))
    for k in range(int(2 * hw / 0.8) + 1):
        xb_ = -hw + k * 0.8
        pulse_bulb(ico("festoon_bulb", (xb_, -1.38, 3.04 - 0.04 * (k % 2)), 0.07, BULB_M[k % 3], shadow=False), k % 3)
    for sx in (dx - 1.25, dx + 1.25):
        box("sconce_arm", sx - 0.03, sx + 0.03, -0.2, 0.0, 1.95, 2.0, POLE)
        ico("sconce_lamp", (sx, -0.25, 2.02), 0.1, WARM_BULB, shadow=False)
    # ---- sign board
    box("sign_rim", -3.6, 3.6, -0.22, 0.0, 3.8, 4.8, CREAM)
    box("sign_board", -3.5, 3.5, -0.3, -0.18, 3.9, 4.7, M(S['signbg'], 0.7))
    neon = S.get('neon')
    sm = M(S['signfg'], 0.5, emit=S['signfg'], strength=(5.0 if neon else 0.35))
    SIGN_MATS.append((sm, neon, S['kind']))
    text(S['text'], (0, -0.33, 4.3), 0.68, sm, extrude=0.04, maxw=5.2 if S['kind'] != 'cookie' else 5.2)
    if kind != 'arcade':
        for sx in (-3.05, 3.05):
            cookie("sign_dot", (sx, -0.4, 4.3), 0.24, 0.08, 'Y', M(S['acc'], 0.6), CREAM, nchips=3, seed=3)
    # ---- emblem on the wall
    zc = (4.8 + H) / 2 + 0.05
    e0 = len(_new)
    mode = emblem(kind, 0.0)
    parts = _new[e0:]
    rig = empty("emblem_" + kind, (0, 0, 0))
    adopt(parts, rig)                                   # parts were built around the origin
    rig.matrix_world = CUR @ Matrix.Translation((0, 0, zc))   # then the rig lifts them to the wall
    box("emb_bracket_L", -0.12, 0.12, -0.2, 0.0, 4.8, 4.8 + (zc - 4.8) * 0.5, CHOC)
    for k, (ddx, ddz, col) in enumerate(((-1.7, 0.7, '#FF7FA8'), (1.7, 0.4, '#FFD166'), (-1.9, -0.7, '#4FC9BE'), (1.8, -0.8, '#C8B6F2'))):
        ico("sparkle", (ddx, -0.12, zc + ddz), 0.1, M(col, 0.5))
    # ---- bunting on the facade
    for (xa, xb) in ((-4.8, -1.4), (1.4, 4.8)):
        pts = [(xa + (xb - xa) * t / 8, -0.22, H - 0.18 - 0.32 * math.sin(math.pi * t / 8)) for t in range(9)]
        for k in range(8):
            rod("bunting_string", pts[k], pts[k + 1], 0.012, M('#FFF6E6'))
        for k in range(1, 8):
            x_, y_, z_ = pts[k]
            bm = bmesh.new()
            tri = [(-0.15, 0, 0), (0.15, 0, 0), (0, 0, -0.32)]
            f1 = [bm.verts.new(q) for q in tri]
            f2 = [bm.verts.new((q[0], q[1] + 0.02, q[2])) for q in tri]
            bm.faces.new(f1)
            bm.faces.new(f2[::-1])
            for a in range(3):
                b_ = (a + 1) % 3
                bm.faces.new([f1[a], f1[b_], f2[b_], f2[a]])
            fo = build("flag", bm, M(FLAG_COL[(k + int(xa) + int(S['cx'])) % 5], 0.8), loc=(x_, y_ - 0.01, z_))
            FLAGS.append((fo, k, fo.rotation_euler[2]))
    # ---- interior
    box("back_panel", -hw + 0.4, hw - 0.4, 5.52, 5.6, 0.19, 3.4, M(S['inner'], 0.9, emit='#FFC070', strength=0.55))
    rr = random.Random(int(S['cx']) + (7 if S['side'] == 'S' else 0))
    for zs in (1.3, 2.0, 2.7):
        box("shelf", -4.5, 4.5, 5.0, 5.52, zs, zs + 0.06, M('#C98A5B'))
        x = -4.4
        while x < 4.2:
            w_ = rr.uniform(0.18, 0.45)
            h_ = rr.uniform(0.2, 0.5)
            box("shelf_item", x, x + w_, 5.1, 5.1 + rr.uniform(0.2, 0.35), zs + 0.06, zs + 0.06 + h_, M(rr.choice(PASTELS), 0.7))
            x += w_ + rr.uniform(0.05, 0.25)
    box("counter", -3.0, 3.0, 3.8, 4.7, 0.19, 1.05, M(S['wall'], 0.9))
    box("counter_top", -3.1, 3.1, 3.7, 4.8, 1.05, 1.12, CREAM)
    for k, x in enumerate((-2.2, -0.8, 0.6, 1.9)):
        disc("plate", (x, 4.25, 1.15), 0.32, 0.04, WHITE, seg=10)
        if kind == 'cookie':
            cookie("counter_cookie", (x, 4.25, 1.2), 0.26, 0.07, 'Z', DOUGH if k % 2 == 0 else DOUGH_D, CHIP if k % 2 == 0 else M('#FFF1D8'), nchips=5, seed=k + 20)
        else:
            ico("counter_item", (x, 4.25, 1.3), 0.15, M(PASTELS[(k + int(S['cx'])) % 7], 0.6))
    for (x, y) in ((-3.0, 2.0), (3.0, 2.0), (0.0, 3.2)):
        box("cord", x - 0.01, x + 0.01, y - 0.01, y + 0.01, 2.95, 3.4, CHOC)
        ico("bulb", (x, y, 2.8), 0.2, WARM_BULB, shadow=False)
    # ---- outside props
    outside(S)
    # ---- chimney (a few shops)
    if S.get('chimney'):
        BRICK = M('#C96B5A', 0.9, brick=(7.0, '#B85C4C', '#E8D9C8'))
        cxh = 3.3
        box("chimney", cxh, cxh + 0.9, 3.5, 4.4, H + 0.3, H + 2.0, BRICK)
        box("chimney_cap", cxh - 0.1, cxh + 1.0, 3.4, 4.5, H + 2.0, H + 2.2, acc)
    # ---- lights (no shadow = cheap)
    for (x, y, z, e, c) in ((-2.5, 2.0, 2.6, 60, '#FFB566'), (2.5, 2.0, 2.6, 60, '#FFB566'), (dx, -1.0, 2.7, 50, '#FFC070')):
        add_light("shop_light", 'POINT', (x, y, z), e, c, 0.3, shadow=False)
    add_light("sign_glow", 'POINT', (0, -2.0, 4.4), 40, '#FFD9A0', 0.3, shadow=False)
    if S['side'] == 'S':
        fl = add_light("south_fill", 'AREA', (0, -9.0, 4.5), 220, '#FFD9B8', 6, shadow=False)
        fl.data.size = 10
        to_track(fl, tuple(CUR @ Vector((0, 0, 3.2))))
    S['hinge'] = hinge
    S['emb'] = (rig, mode)
    S['hinge_base'] = hinge.rotation_euler[2]
    SHOPS_BUILT.append(S)
    at(Matrix.Identity(4))


def add_light(name, kind, loc, energy, hexcol, size=0.3, shadow=True):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = srgb(hexcol)
    if kind == 'POINT':
        ld.shadow_soft_size = size
    try:
        ld.use_shadow = shadow
    except Exception:
        pass
    o = bpy.data.objects.new(name, ld)
    o.location = CUR @ Vector(loc)
    scene.collection.objects.link(o)
    return o


# ======================================================================
# The ten shops
# ======================================================================
SHOP_LIST = [
    dict(kind='toy', cx=-20, side='N', H=8.0, roof='gable', door_x=0.0, wall='#FFE08A', base='#F7B267', acc='#F25C54',
         awnA='#F25C54', awnB='#FFF6E6', signbg='#3D5A9E', signfg='#FFE9A8', doorc='#3D8BD9', floor='#FFE9C2', inner='#FFF3D6',
         text='Toy Box', chalk='Toys!\nNew bears'),
    dict(kind='candy', cx=-10, side='N', H=7.8, roof='stepped', door_x=-2.8, wall='#BDE8F5', base='#FF9EBB', acc='#FF7FA8',
         awnA='#FF7FA8', awnB='#FFFFFF', signbg='#FF5C8A', signfg='#FFFFFF', doorc='#FF5C8A', floor='#FFD7E4', inner='#FFEAF2',
         text='Sweet Tooth Candy', chalk='Fresh\nfudge'),
    dict(kind='cookie', cx=0, side='N', H=7.6, roof='flat', door_x=0.0, wall='#F8B4CB', base='#A6E3CF', acc='#C8B6F2',
         awnA='#4FC9BE', awnB='#FFF6E6', signbg='#4A2A1C', signfg='#FFD7E4', doorc='#B9743F', floor='#FFF1D8', inner='#FFF3E0',
         text='Kevin Cookie Company', chalk='Fresh\nCookies!', chimney=True),
    dict(kind='train', cx=10, side='N', H=7.6, roof='flat', door_x=2.8, wall='#FFB88C', base='#7A9E9F', acc='#3D5A6C',
         awnA='#3D8BD9', awnB='#FFF6E6', signbg='#2F4B5C', signfg='#FFD166', doorc='#2F6F9E', floor='#E8D8C0', inner='#FFEBD6',
         text='Choo Choo Hobbies', chalk='Trains\n& planes'),
    dict(kind='bike', cx=20, side='N', H=7.5, roof='stepped', door_x=-2.8, wall='#A6E3CF', base='#E9A07A', acc='#FF9E6B',
         awnA='#FF9E6B', awnB='#FFF6E6', signbg='#264653', signfg='#F4F1DE', doorc='#E76F51', floor='#E3E8DC', inner='#EEFAF2',
         text='Spoke & Roll', chalk='Bikes\nskates'),
    dict(kind='book', cx=-20, side='S', H=8.2, roof='gable', door_x=2.8, wall='#9CC8F0', base='#C96B5A', acc='#2A6F97',
         awnA='#FFD166', awnB='#FFF6E6', signbg='#1D3557', signfg='#FFE9A8', doorc='#8D5B3A', floor='#D8C7A8', inner='#FFF1D6',
         text='Page Turner Books', chalk='Story time\n4 pm'),
    dict(kind='ice', cx=-10, side='S', H=7.7, roof='stepped', door_x=0.0, wall='#FFE0EC', base='#7FD6C4', acc='#7FD6C4',
         awnA='#7FD6C4', awnB='#FFFFFF', signbg='#FF7FA8', signfg='#FFFFFF', doorc='#4FC9BE', floor='#FFD7E4', inner='#FFF0F5',
         text='Scoops Ice Cream', chalk='Scoops\ntoday'),
    dict(kind='pet', cx=0, side='S', H=7.4, roof='flat', door_x=-2.8, wall='#C9E4A0', base='#8FB86A', acc='#7A4B2A',
         awnA='#FF9E6B', awnB='#FFF6E6', signbg='#7A4B2A', signfg='#FFF6E6', doorc='#B9743F', floor='#E8DDB8', inner='#F6FBE6',
         text='Puppy Pals Pet Shop', chalk='Puppies!\nCome in', chimney=True),
    dict(kind='comic', cx=10, side='S', H=8.0, roof='gable', door_x=2.8, wall='#C8B6F2', base='#5C4E7A', acc='#FFD166',
         awnA='#FFD166', awnB='#5C4E7A', signbg='#2B2B5C', signfg='#FFD166', doorc='#FF5C8A', floor='#D8CFEF', inner='#EFE9FF',
         text='Pixel Comics & Games', chalk='New\ncomics!'),
    dict(kind='arcade', cx=20, side='S', H=7.8, roof='stepped', door_x=0.0, wall='#6CC5C0', base='#2B2B5C', acc='#FF5C8A',
         awnA='#FF5C8A', awnB='#2B2B5C', signbg='#1B1B3A', signfg='#7DF9FF', doorc='#FF5CD9', floor='#3A3A6A', inner='#D8F5F2',
         text='Arcade Alley', chalk='Tokens\n2 for 1', neon=True),
]
for S in SHOP_LIST:
    S['door_t'] = []
    shop(S)


# ======================================================================
# Street: ground, road, sidewalks, crosswalk, plain end houses
# ======================================================================
at(Matrix.Identity(4))
box("grass", -300, 300, -300, 300, -0.6, -0.1, M('#B7E9B2'))
box("road", -300, 300, -13.0, -5.0, -0.3, -0.02, M('#8E8CA8', 0.95))
for i in range(-14, 40):
    box("lane", i * 3.2 - 0.8, i * 3.2 + 0.8, -9.08, -8.92, -0.03, 0.005, CREAM)
for (cy0, cy1, wy0, wy1, ty0) in ((-5.0, -4.55, -4.55, 0.0, -4.5), (-13.45, -13.0, -18.0, -13.45, -18.0)):
    box("curb", -60, 60, cy0, cy1, 0.0, 0.2, M('#F6DDE4'))
    box("walk_base", -60, 60, wy0, wy1, 0.0, 0.12, SIDEWALK_G)
    for ix in range(35):
        for iy in range(3):
            x0 = -26.25 + ix * 1.5
            y0 = ty0 + iy * 1.5
            box("tile", x0 + 0.03, x0 + 1.47, y0 + 0.03, y0 + 1.47, 0.12, 0.15, TILE_VAR[(ix * 7 + iy * 3) % 3])
for k in range(8):   # zebra crossing at x = 12.5
    y0 = -12.6 + k * 0.9
    box("zebra", 11.4, 13.6, y0, y0 + 0.45, -0.03, 0.01, CREAM)
rnd = random.Random(7)
for k in range(20):   # sidewalk gum, crumbs, leaves
    for ylo, yhi in ((-4.2, -0.6), (-17.4, -13.8)):
        if k < 8:
            disc("gum", (rnd.uniform(-24, 24), rnd.uniform(ylo, yhi), 0.152), 0.05, 0.006, M('#FF9EBB', 0.5), seg=7)
        elif k < 14:
            sz = rnd.uniform(0.02, 0.045)
            ico("crumb", (rnd.uniform(-24, 24), rnd.uniform(ylo, yhi), 0.16), (sz, sz, sz * 0.6), M('#C98A4B', 0.9))
        else:
            disc("leaf", (rnd.uniform(-24, 24), rnd.uniform(ylo, yhi), 0.153), 0.09, 0.004, M(['#F4A261', '#E9C46A', '#E76F51'][k % 3], 0.9), seg=5)
for k, (hx, hy) in enumerate(((0, 0), (0, 0.5), (-0.3, 1.0), (0.3, 1.0), (0, 1.5), (-0.3, 2.0), (0.3, 2.0), (0, 2.5))):   # hopscotch
    box("hop", -22.9 + hx, -22.45 + hx, -3.7 + hy, -3.3 + hy, 0.15, 0.158, M(PASTELS[k % 7], 0.8))


def house(cx, side, W, H, col, seed=0):
    at(shop_matrix(cx, side))
    r_ = random.Random(seed)
    hw = W / 2
    box("h_body", -hw, hw, 0, 6, 0, H, M(col, 0.9, bump=(45, 0.25)))
    box("h_cornice", -hw - 0.2, hw + 0.2, -0.3, 6.2, H, H + 0.35, CREAM)
    box("h_base", -hw, hw, -0.05, 0.1, 0, 0.8, M(shade(col, 0.88)))
    n = max(2, int(W // 3.2))
    for (zz, hh) in ((1.0, 1.7), (3.9, 1.5)):
        if zz + hh > H - 0.3:
            continue
        for k in range(n):
            x = -hw + W * (k + 0.5) / n
            frame(x - 0.7, x + 0.7, zz, zz + hh, CREAM, t=0.12, y0=-0.1, y1=0.05)
            box("h_glass", x - 0.7, x + 0.7, -0.05, 0.0, zz, zz + hh, GLOW_GLASS if r_.random() < 0.7 else GLASS_DARK, shadow=False)
    box("h_door", -0.8, 0.8, -0.1, 0.0, 0.1, 2.3, M(r_.choice(PASTELS), 0.7))
    at(Matrix.Identity(4))


HCOL = ['#FFE9A8', '#CFC2F5', '#FFD2C2', '#BDE8F5', '#E6F5C0', '#F8B4CB']
for si, side in enumerate(('N', 'S')):
    for sgn in (1, -1):
        edge = 25.0
        for ki in range(4 if sgn > 0 else 1):
            W = 10.5 + (ki % 3)
            house(sgn * (edge + W / 2), side, W, 6.4 + (ki * 5 % 4) * 0.6, HCOL[(ki + si * 3 + (sgn > 0)) % 6], seed=ki + si * 10 + (sgn > 0) * 20)
            edge += W

# ======================================================================
# Street dressing
# ======================================================================
LAMP_X = (-25, -15, -5, 5, 15, 25)
for side_y, sg in ((-4.4, 1), (-13.6, -1)):   # sg points toward the road
    for x in LAMP_X:
        disc("lamp_base", (x, side_y, 0.35), 0.16, 0.4, POLE, seg=8, taper=0.8)
        disc("lamp_pole", (x, side_y, 2.2), 0.06, 4.0, POLE, seg=6)
        ico("lamp_head", (x, side_y, 4.3), 0.3, M('#FFE7B0', 0.4, emit='#FFC070', strength=2), shadow=False)
        disc("lamp_cap", (x, side_y, 4.65), 0.22, 0.06, POLE, seg=8, taper=0.5)
        box("lamp_arm", x - 0.02, x + 0.02, min(side_y, side_y - sg * 0.5), max(side_y, side_y - sg * 0.5), 3.2, 3.24, POLE)
        ico("lamp_basket", (x, side_y - sg * 0.5, 3.1), (0.18, 0.18, 0.13), M('#9BE5B5'))
        for q in range(3):
            ico("lamp_flower", (x + (q - 1) * 0.1, side_y - sg * 0.5, 3.28), 0.07, M(PASTELS[(q + int(x)) % 7], 0.6))
        add_light("lamp_light", 'POINT', (x, side_y, 4.1), 30, '#FFC070', 0.3, shadow=False)
        box("lamp_banner", -0.2, 0.2, -0.01, 0.01, -0.55, 0.0, M(PASTELS[int(x) % 7], 0.7), rot=Matrix.Translation((x + 0.22, side_y, 3.6)))

# string lights across the street, pole head to pole head, with bunting on some
for x in LAMP_X:
    p0, p1 = Vector((x, -4.4, 4.15)), Vector((x, -13.6, 4.15))
    N = 17
    pts = [p0.lerp(p1, t / N) - Vector((0, 0, 0.9 * math.sin(math.pi * t / N))) for t in range(N + 1)]
    for a, b in zip(pts, pts[1:]):
        rod("string", a, b, 0.012, POLE)
    for t in range(1, N):
        pulse_bulb(ico("string_bulb", tuple(pts[t] - Vector((0, 0, 0.1))), 0.07, BULB_M[(t + int(x)) % 3], shadow=False), (t + int(x)) % 3)
    if int(x) % 20 != 0:
        for t in range(1, N, 2):
            x_, y_, z_ = pts[t] + Vector((0.0, 0.0, -0.1))
            bm = bmesh.new()
            tri = [(-0.14, 0, 0), (0.14, 0, 0), (0, 0, -0.3)]
            f1 = [bm.verts.new(q) for q in tri]
            f2 = [bm.verts.new((q[0], q[1] + 0.02, q[2])) for q in tri]
            bm.faces.new(f1)
            bm.faces.new(f2[::-1])
            for a_ in range(3):
                b_ = (a_ + 1) % 3
                bm.faces.new([f1[a_], f1[b_], f2[b_], f2[a_]])
            build("street_flag", bm, M(FLAG_COL[(t + int(x)) % 5], 0.8), loc=(x_ + 0.3, y_, z_))

# lollipop trees at slot centres (not in front of the cookie shop)
TREES = []
MINT_B = M('#A6E3CF', 0.85, brick=(6.0, '#92D9C3', '#E9F7F0'))
for (x, y, col) in ((-25, -3.6, '#FFC49B'), (-15, -3.6, '#9BE5B5'), (15, -3.6, '#C8B6F2'), (25, -3.6, '#FFC49B'),
                    (-25, -14.4, '#C8B6F2'), (-15, -14.4, '#FFC49B'), (15, -14.4, '#9BE5B5'), (25, -14.4, '#C8B6F2')):
    box("planter", x - 0.5, x + 0.5, y - 0.5, y + 0.5, 0.15, 0.5, MINT_B)
    if x < 24:   # walk version: a low bush, so nothing stands between the walker and a shop front
        parts = [ico("bush", (x, y, 0.85), (0.55, 0.55, 0.4), M(col, 0.9)), ico("bush_hi", (x - 0.2, y - 0.2, 1.05), (0.22, 0.22, 0.18), WHITE)]
        rig = empty("tree_rig", (x, y, 0.5))
        adopt(parts, rig)
        TREES.append(rig)
        continue
    disc("trunk", (x, y, 1.35), 0.08, 1.7, M('#B7835A'), seg=6)
    parts = [ico("canopy", (x, y, 2.9), (0.9, 0.9, 0.85), M(col, 0.9)), ico("canopy_hi", (x - 0.3, y - 0.3, 3.2), (0.35, 0.35, 0.3), WHITE)]
    rig = empty("tree_rig", (x, y, 2.2))
    adopt(parts, rig)
    TREES.append(rig)

# hydrants, bins, mailbox, benches
for (x, y) in ((-7.6, -4.1), (-22.5, -14.1), (8.0, -14.2)):
    disc("hydrant", (x, y, 0.45), 0.14, 0.6, M('#FF7FA8', 0.6), seg=8)
    ico("hydrant_dome", (x, y, 0.78), (0.15, 0.15, 0.12), M('#FF7FA8', 0.6))
    box("hydrant_nub", x - 0.18, x + 0.18, y - 0.04, y + 0.04, 0.5, 0.58, GOLD)
for (x, y) in ((7.4, -4.1), (-4.0, -14.1), (16.0, -4.1)):
    disc("bin", (x, y, 0.5), 0.26, 0.7, M('#A6E3CF'), seg=8, taper=1.1)
    disc("bin_lid", (x, y, 0.88), 0.29, 0.06, M('#4FC9BE'), seg=8)
box("mailbox", -17.9, -17.5, -4.3, -3.9, 0.15, 1.2, M('#3D8BD9', 0.5))
disc("mailbox_top", (-17.7, -4.1, 1.2), 0.2, 0.4, M('#3D8BD9', 0.5), seg=8, axis='Y')
for (bx, by, ty_) in ((-4.0, -4.2, 1), (3.8, -13.7, -1)):
    box("bench_seat", bx - 0.8, bx + 0.8, by - 0.25, by + 0.25, 0.5, 0.56, M('#C98A5B'))
    box("bench_back", bx - 0.8, bx + 0.8, by + ty_ * 0.22, by + ty_ * 0.28, 0.56, 1.0, M('#C98A5B'))
    for sx in (-0.7, 0.7):
        box("bench_leg", bx + sx - 0.03, bx + sx + 0.03, by - 0.22, by + 0.22, 0.15, 0.5, POLE)

# popcorn cart on the south sidewalk
PX, PY = -14.2, -15.2
box("cart_body", PX - 0.7, PX + 0.7, PY - 0.45, PY + 0.45, 0.45, 1.2, M('#E63946', 0.6))
box("cart_stripe", PX - 0.71, PX + 0.71, PY - 0.46, PY + 0.46, 0.8, 1.0, WHITE)
box("cart_glass", PX - 0.6, PX + 0.6, PY - 0.4, PY + 0.4, 1.2, 1.75, M('#CFEFFF', 0.1, emit='#FFD9A0', strength=0.8, alpha=0.4))
for j in range(10):
    ico("popcorn", (PX + (j % 5 - 2) * 0.2, PY + (j // 5 - 0.5) * 0.3, 1.25 + 0.04 * (j % 3)), 0.09, WHITE)
disc("cart_pole", (PX, PY, 2.2), 0.03, 1.0, POLE, seg=6)
for k in range(8):
    a0, a1 = TAU * k / 8, TAU * (k + 1) / 8
    bm = bmesh.new()
    cvs = [bm.verts.new((PX, PY, 2.9))] + [bm.verts.new((PX + math.cos(a) * 1.3, PY + math.sin(a) * 1.3, 2.55)) for a in (a0, a1)]
    bm.faces.new(cvs)
    build("cart_umb", bm, M('#E63946' if k % 2 == 0 else '#FFFFFF', 0.7))
for sx in (-0.5, 0.5):
    disc("cart_wheel", (PX + sx, PY - 0.5, 0.3), 0.28, 0.05, CHOC2, seg=10, axis='Y')


def make_car(col):
    car = empty("car")
    bm_ = M(col, 0.5)
    pbox("car_body", -1.6, 1.6, -0.75, 0.75, 0.35, 0.85, bm_, (0, 0, 0), car)
    pbox("car_cabin", -0.7, 0.9, -0.65, 0.65, 0.85, 1.35, M('#CFEFFF', 0.2), (0, 0, 0), car)
    pbox("car_roof", -0.8, 1.0, -0.7, 0.7, 1.35, 1.42, bm_, (0, 0, 0), car)
    pbox("car_bumper", 1.55, 1.7, -0.7, 0.7, 0.3, 0.45, M('#FFF6E6'), (0, 0, 0), car)
    pbox("car_bumper_b", -1.7, -1.55, -0.7, 0.7, 0.3, 0.45, M('#FFF6E6'), (0, 0, 0), car)
    for sy in (-1, 1):
        child(ico("car_light", (1.62, sy * 0.5, 0.65), (0.08, 0.14, 0.1), M('#FFF3C4', 0.3, emit='#FFE9A0', strength=12), shadow=False), car)
        child(ico("car_tail", (-1.62, sy * 0.5, 0.65), (0.05, 0.12, 0.08), M('#FF5C5C', 0.3, emit='#FF3030', strength=4), shadow=False), car)
    wheels = []
    for (wx, sy) in ((1.0, 1), (1.0, -1), (-1.0, 1), (-1.0, -1)):
        w_ = disc("car_wheel", (0, 0, 0), 0.35, 0.2, M('#2B2B33', 0.9), seg=10, axis='Y')
        w_.location = (wx, sy * 0.78, 0.35)
        w_.parent = car
        hub = disc("car_hub", (0, sy * 0.11, 0), 0.16, 0.04, M('#FFF6E6'), seg=8, axis='Y')
        hub.parent = w_
        wheels.append(w_)
    return car, wheels


def car_lights(car):
    sp = bpy.data.lights.new("car_headlight", 'SPOT')
    sp.energy, sp.color, sp.spot_size, sp.spot_blend = 600, srgb('#FFE9A8'), math.radians(70), 0.7
    try:
        sp.use_shadow = False
    except Exception:
        pass
    o = bpy.data.objects.new("car_headlight", sp)
    scene.collection.objects.link(o)
    o.parent = car
    o.location = (1.7, 0, 0.6)
    o.rotation_euler = (0, -math.pi / 2 + 0.12, 0)


for (x, y, col, rz) in ((-43.0, -12.1, '#FF9E6B', 0.0), (43.0, -6.0, '#7FB5FF', math.pi)):   # parked
    c_, _w = make_car(col)
    c_.location = (x, y, 0.0)
    c_.rotation_euler = (0, 0, rz)

# ======================================================================
# Sky, sun, clouds, hills, clock tower, birds
# ======================================================================
def sky_mat():
    m = bpy.data.materials.new("sky_grad")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sp = nt.nodes.new('ShaderNodeSeparateXYZ')
    mr = nt.nodes.new('ShaderNodeMapRange')
    cr = nt.nodes.new('ShaderNodeValToRGB')
    em = nt.nodes.new('ShaderNodeEmission')
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(tc.outputs['Object'], sp.inputs['Vector'])
    nt.links.new(sp.outputs['Z'], mr.inputs['Value'])
    mr.inputs['From Min'].default_value = -20.0
    mr.inputs['From Max'].default_value = 330.0
    nt.links.new(mr.outputs['Result'], cr.inputs['Fac'])
    stops = [(0.0, '#FFE6C4'), (0.1, '#FFE9D0'), (0.28, '#CFE6F7'), (0.55, '#93C8F0'), (1.0, '#5FA3E6')]
    els = cr.color_ramp.elements
    els[0].position, els[0].color = stops[0][0], (*srgb(stops[0][1]), 1)
    els[1].position, els[1].color = stops[1][0], (*srgb(stops[1][1]), 1)
    for pos, hx in stops[2:]:
        e = els.new(pos)
        e.color = (*srgb(hx), 1)
    nt.links.new(cr.outputs['Color'], em.inputs['Color'])
    em.inputs['Strength'].default_value = 1.0
    nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
    return m


bm_sky = bmesh.new()
bmesh.ops.create_icosphere(bm_sky, subdivisions=3, radius=450)
build("skydome", bm_sky, sky_mat(), loc=(0, -9, 0), shadow=False)
SUN_DIR = Vector((0.45, -0.62, 0.64)).normalized()   # morning sun: south-east, about 40 degrees high
SP = Vector((0, -9, 0)) + SUN_DIR * 400
for (rad, hx, st, dxo) in ((34, '#FFE2B0', 1.6, 2.0), (23, '#FFEFC4', 2.4, 1.0), (14, '#FFFAE8', 5.0, 0.0)):
    ico("sun_layer", (SP.x - dxo * 3, SP.y, SP.z), (0.3, rad, rad), M(hx, 0.5, emit=hx, strength=st), sub=2, shadow=False)
CLOUD_RIGS = []
for (cx, cy, cz, sc, col) in ((260, -90, 95, 1.6, '#FFFFFF'), (200, 40, 120, 2.0, '#F4F8FF'), (280, -190, 80, 1.3, '#FFF1E0'),
                              (120, -60, 70, 1.1, '#FFFFFF'), (300, 120, 140, 2.0, '#EAF2FF')):
    k0 = len(_new)
    for (dx_, dz_, s_) in ((0, 0, 1.4), (1.5, 0.2, 1.1), (-1.5, -0.1, 1.0), (0.6, 0.7, 0.9)):
        ico("cloud", (cx + dx_ * sc * 6, cy + dx_ * sc * 2, cz + dz_ * sc * 5), (s_ * sc * 14, s_ * sc * 8, s_ * sc * 5), M(col, 1.0, emit=col, strength=1.0), shadow=False)
    rig = empty("cloud_rig", (0, 0, 0))
    adopt(_new[k0:-1], rig)
    CLOUD_RIGS.append(rig)
for (x, y, z, sx, sy, sz, col) in ((260, -60, -8, 90, 55, 40, '#A9D8B8'), (300, 90, -8, 110, 70, 50, '#9ED0A8'),
                                   (240, -170, -8, 80, 60, 30, '#B7DDC9'), (330, -20, -8, 140, 90, 60, '#8CC9B0')):
    ico("hill", (x, y, z), (sx, sy, sz), M(col, 1.0, emit=col, strength=0.25), sub=1, shadow=False)
TX = 110   # clock tower at the end of the street
box("tower", TX - 4, TX + 4, -13, -5, 0, 22, M('#F4D8B8', 0.9, bump=(30, 0.2)))
box("tower_band", TX - 4.4, TX + 4.4, -13.4, -4.6, 20.5, 21.5, M('#FF9EBB'))
pr = disc("tower_roof", (TX, -9, 25.5), 7.0, 8.0, M('#7FB5C9', 0.8), seg=4, taper=0.02)
pr.rotation_euler = (0, 0, math.radians(45))
ico("clock_face", (TX - 4.1, -9, 16), (0.2, 2.6, 2.6), M('#FFF6E0', 0.5, emit='#FFE2A8', strength=1.5), shadow=False)
box("clock_h1", TX - 4.4, TX - 4.2, -9.15, -8.85, 16.0, 18.0, CHOC)
box("clock_h2", TX - 4.4, TX - 4.2, -9.0, -7.6, 15.85, 16.15, CHOC)
for k in range(4):
    box("tower_win", TX - 4.05, TX - 3.95, -12 + k * 2.2, -11 + k * 2.2, 5, 8, GLOW_GLASS, shadow=False)
for (x, y) in ((70, -4.5), (74, -13.5), (82, -4.5), (86, -13.5), (96, -4.5), (95, -13.5)):
    disc("ftrunk", (x, y, 1.5), 0.15, 3, M('#B7835A'), seg=6)
    ico("fcanopy", (x, y, 4.0), (1.5, 1.5, 1.6), M(PASTELS[int(x) % 7], 0.9))
BIRDS = []
for k in range(5):
    b_ = empty("bird", (0, 0, 0))
    child(ico("bird_body", (0, 0, 0), (0.45, 0.25, 0.22), M('#4A3A5A', 0.9), shadow=False), b_)
    wings = [pbox("bird_wing", -0.3, 0.3, sy * 0.15, sy * 1.2, -0.02, 0.02, M('#4A3A5A', 0.9), (0, sy * 0.15, 0), b_) for sy in (1, -1)]
    BIRDS.append((b_, wings, k))

# ======================================================================
# People
# ======================================================================
# ---------------- the walk: a slow stroll along the street, head turning toward each shop, no zoom ----------------
WALK_V = 0.05                  # metres per frame at full pace: 1.2 m/s
X0, X1 = -41.0, 28.0           # start and end x of the walk
LENS, CAM_Z, PITCH = 21.0, 1.65, 0.19
Y_MID, Y_AMP = -9.0, 1.5       # the walker drifts toward the side it looks at
PSI_FIRST, PSI_SECOND = math.radians(24), math.radians(34)   # head turn (left positive) at the first and second shop of a pair
RAMP = 60
_N = int((X1 - X0) / WALK_V) + RAMP
_v = [min(1.0, f / RAMP, (_N - f) / RAMP) for f in range(_N + 1)]
_c, _acc = [], 0.0
for _vv in _v:
    _acc += _vv
    _c.append(_acc)
CAM_X = [X0 + (X1 - X0) * c_ / _c[-1] for c_ in _c]     # CAM_X[f - 1] is the x position at frame f
FRAMES = len(CAM_X)
VIEW_KEYS = []     # (x, psi, shop index): the head turns to this shop when the walker is at x
for cx_, i_first, i_second, sgn_ in ((-20, 0, 5, 1), (-10, 6, 1, -1), (0, 2, 7, 1), (10, 8, 3, -1), (20, 4, 9, 1)):
    VIEW_KEYS.append((cx_ - 11.5, sgn_ * PSI_FIRST, i_first))
    VIEW_KEYS.append((cx_ - 6.5, -sgn_ * PSI_SECOND, i_second))
PSI_PTS = [(X0, 0.0)] + [(x_, p_) for (x_, p_, _i) in VIEW_KEYS] + [(VIEW_KEYS[-1][0] + 8.0, 0.0), (X1 + 1.0, 0.0)]


def psi_of(x):
    for (xa, pa), (xb, pb) in zip(PSI_PTS, PSI_PTS[1:]):
        if xa <= x <= xb:
            u = (x - xa) / (xb - xa)
            return pa + (pb - pa) * u * u * (3 - 2 * u)
    return 0.0


VIEW_T = {}        # shop index -> frame at which the walker looks at it
for (x_, p_, i_) in VIEW_KEYS:
    VIEW_T[i_] = 1 + next(i for i, cx__ in enumerate(CAM_X) if cx__ >= x_)
def beat_keys(step):
    """Key frames every `step` frames, on the beat grid, from before frame 1 to after the last frame."""
    return [BEAT0 + k * step for k in range(int((-10 - BEAT0) // step), int((FRAMES + 12 - BEAT0) // step) + 1)]


scene.render.fps, scene.render.fps_base = 24, 1.0
scene.frame_start, scene.frame_end = 1, FRAMES


def kf(o, path_, idx, f, val, kind='BEZIER'):
    bpy.context.preferences.edit.keyframe_new_interpolation_type = kind
    if idx is None:
        setattr(o, path_, val)
        o.keyframe_insert(path_, frame=f)
    else:
        getattr(o, path_)[idx] = val
        o.keyframe_insert(path_, index=idx, frame=f)


def kf_socket(mat, name, f, val, kind='BEZIER'):
    bpy.context.preferences.edit.keyframe_new_interpolation_type = kind
    sk = mat.node_tree.nodes["Principled BSDF"].inputs[name]
    sk.default_value = val
    sk.keyframe_insert('default_value', frame=f)


SKINS = ['#F2C6A0', '#E8B48C', '#C98E62', '#8D5B3A', '#6B4129', '#F6D5B8']
HAIRS = ['#4B2E24', '#1F1B1A', '#C98A4B', '#E3B04B', '#7A3B1E', '#A9A9B5', '#FF7FA8']
SHIRTS = ['#FF7FA8', '#FFD166', '#4FC9BE', '#C8B6F2', '#FF9E6B', '#7FB5FF', '#9BE5B5', '#E63946', '#F4F1DE']
PANTS = ['#3D5A6C', '#5C4E7A', '#7A5C4E', '#C8B6F2', '#4FC9BE', '#E07A5F', '#2F4B5C']
prnd = random.Random(21)


def person(name, kid=False, dress=None, hat=None, shirt=None, pants=None, skin=None, hair=None):
    shirt = shirt or prnd.choice(SHIRTS)
    pants = pants or prnd.choice(PANTS)
    skin = skin or prnd.choice(SKINS)
    hair = hair or prnd.choice(HAIRS)
    s_ = 0.78 if kid else prnd.uniform(1.05, 1.18)
    root = empty(name)
    root.scale = (s_, s_, s_)
    pbox("torso", -0.13, 0.13, -0.21, 0.21, 0.55, 1.1, M(shirt), (0, 0, 0), root)
    pbox("hips", -0.12, 0.12, -0.17, 0.17, 0.5, 0.6, M(pants), (0, 0, 0), root)
    if dress:
        pbox("skirt", -0.19, 0.19, -0.25, 0.25, 0.3, 0.62, M(dress), (0, 0, 0), root)
    child(ico(name + "_head", (0, 0, 1.3), 0.17, M(skin)), root)
    child(ico(name + "_hair", (-0.02, 0, 1.4), (0.18, 0.18, 0.11), M(hair)), root)
    if hat:
        child(box(name + "_hat", -0.2, 0.22, -0.19, 0.19, 1.46, 1.53, M(hat)), root)
        child(ico(name + "_hatc", (-0.02, 0, 1.5), (0.17, 0.17, 0.08), M(hat)), root)
    for sy in (-1, 1):
        child(ico(name + "_eye", (0.15, sy * 0.06, 1.32), 0.03, CHOC2), root)
    child(ico(name + "_nose", (0.17, 0, 1.28), 0.03, M(skin)), root)
    legs, arms = [], []
    for sy in (1, -1):
        legs.append(pbox("leg", -0.07, 0.07, sy * 0.1 - 0.06, sy * 0.1 + 0.06, 0, 0.55, M(pants), (0, sy * 0.1, 0.55), root))
        a = pbox("arm", -0.05, 0.05, sy * 0.26 - 0.05, sy * 0.26 + 0.05, 0.62, 1.05, M(shirt), (0, sy * 0.26, 1.05), root)
        child(ico(name + "_hand", (0, 0, -0.45), 0.06, M(skin)), a)
        arms.append(a)
    return {'root': root, 'legs': legs, 'arms': arms}


def give_bag(p, col=None):
    col = col or prnd.choice(PASTELS)
    a = p['arms'][1]
    child(box("bag", -0.1, 0.1, -0.05, 0.05, -0.85, -0.5, M(col, 0.6)), a)
    child(box("bag_h", -0.05, 0.05, -0.03, 0.03, -0.5, -0.4, WHITE), a)


def give_balloon(p, col=None):
    col = col or prnd.choice(('#FF5C8A', '#4FC9BE', '#FFD166', '#7FB5FF'))
    b = child(ico("balloon", (0.0, 0.3, 2.55), (0.27, 0.27, 0.33), M(col, 0.25)), p['root'])
    child(box("balloon_string", -0.006, 0.006, 0.294, 0.306, 0.7, 2.25, WHITE, shadow=False), p['root'])
    for f in beat_keys(BEAT / 2):
        kf(b, 'location', 2, f, 2.55 + 0.1 * PUNCH * math.sin((f - BEAT0) / (2 * BEAT) * TAU + len(col)))


def give_cone(p, scoops):
    c0 = len(_new)
    cone((0.08, 0.0, -0.62), scoops, 0.6)
    for o in _new[c0:]:
        child(o, p['arms'][1])


def idle(p, ph=0.0, kid=False):
    """Standing person: a slow sway every two beats. A kid also bends the knees a little on every beat."""
    for f in beat_keys(BEAT / 4):
        z = 0.03 * PUNCH * (1 - math.cos((f - BEAT0) / BEAT * TAU)) / 2 if kid else 0.015 * PUNCH * math.sin((f - BEAT0) / (2 * BEAT) * TAU + ph)
        kf(p['root'], 'location', 2, f, z)
        kf(p['arms'][0], 'rotation_euler', 1, f, 0.12 * PUNCH * math.sin((f - BEAT0) / (2 * BEAT) * TAU + ph))


def rest(p, f):
    for l in p['legs'] + p['arms']:
        kf(l, 'rotation_euler', 1, f, 0.0)


def walk(p, f0, f1, period=25, amp=0.6, bob=0.04, off=0.0):
    """Walk cycle on the global beat grid: with period 25 a foot lands on every beat, with period 12.5 on every half beat.
    `off` shifts a walker by a fraction of the period (a quarter period puts the footfalls between the beats)."""
    q = period / 4
    G = BEAT0 - q + off                       # the legs are at full spread (a footfall) at G + q + n * period / 2
    k = math.ceil((f0 - G) / q - 1e-9)
    while True:
        f = G + k * q
        if f > f1 + 0.01 or f > FRAMES + 12:
            break
        if f >= -10:
            ph = (f - G) / period * TAU
            a = amp * math.sin(ph)
            for i, l in enumerate(p['legs']):
                kf(l, 'rotation_euler', 1, f, a * (1 if i == 0 else -1))
            for i, ar in enumerate(p['arms']):
                kf(ar, 'rotation_euler', 1, f, -a * 0.8 * (1 if i == 0 else -1))
            kf(p['root'], 'location', 2, f, abs(math.cos(ph)) * bob * PB)   # the body is lowest when the foot lands
        k += 1


orn = random.Random(77)


def go(p, wps, period=25, amp=0.6, bob=0.04):
    """wps = [(frame, x, y), ...] in world units. Keys location, heading and the walk cycle."""
    root = p['root']
    off = orn.choice((0, 0, 0, period / 2, period / 2, period / 4))   # most walkers land on the beat, some on the half beat
    for (f, x, y) in wps:
        kf(root, 'location', 0, f, x, 'LINEAR')
        kf(root, 'location', 1, f, y, 'LINEAR')
    last_h = None
    for i in range(len(wps) - 1):
        f0, x0, y0 = wps[i]
        f1, x1, y1 = wps[i + 1]
        if math.hypot(x1 - x0, y1 - y0) < 1e-4:
            rest(p, f0)
            rest(p, f1)
            kf(root, 'location', 2, f0, 0.0)
            kf(root, 'location', 2, f1, 0.0)
            continue
        h = math.atan2(y1 - y0, x1 - x0)
        if last_h is not None:
            while h - last_h > math.pi:
                h -= TAU
            while h - last_h < -math.pi:
                h += TAU
        kf(root, 'rotation_euler', 2, f0, h)
        if f1 - 4 > f0:
            kf(root, 'rotation_euler', 2, f1 - 4, h)
        last_h = h
        walk(p, f0, f1, period, amp, bob, off)
    rest(p, wps[-1][0])
    kf(root, 'location', 2, wps[-1][0], 0.0)


V = 0.055   # metres per frame: a calm walk


def lp(S, x, y):
    v = shop_matrix(S['cx'], S['side']) @ Vector((x, y, 0))
    return (v.x, v.y)


def route(f0, pts, v=V):
    out, f = [(f0, pts[0][0], pts[0][1])], f0
    for a, b in zip(pts, pts[1:]):
        f += max(1.0, math.hypot(b[0] - a[0], b[1] - a[1]) / v)
        out.append((f, b[0], b[1]))
    return out


def dist(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


er = random.Random(4)
END = FRAMES
SLOT_START = {si: VIEW_T[si] - 45 for si in VIEW_T}      # shoppers use the door when the walker looks at the shop


def shuttle(a, b, v, f0=-30, pause=14):
    """Waypoints that pace between points a and b until after the last frame."""
    pts, f, cur, tgt = [(f0, a[0], a[1])], f0, a, b
    while f < END + 60:
        f += math.hypot(tgt[0] - cur[0], tgt[1] - cur[1]) / v
        pts.append((f, tgt[0], tgt[1]))
        f += pause
        pts.append((f, tgt[0], tgt[1]))
        cur, tgt = tgt, (a if tgt == b else b)
    return pts


# --- shoppers: every shop gets people walking in and out, timed so the camera sees them
for i, S in enumerate(SHOP_LIST):
    X = S['door_x'] + 0.25
    s0 = SLOT_START[i]
    evs = [('L', s0 + 38), ('E', s0 + 52)] + [(er.choice('LE'), er.randint(10, END - 60)) for _ in range(2)]
    for q, (kind_, t) in enumerate(evs):
        off = (-0.7, 0.0, 0.7, -0.35)[q % 4]
        if kind_ == 'E':
            kid = (q + i) % 3 == 0
            pin = person("enter_%s_%d" % (S['kind'], q), kid=kid, hat=('#FF7FA8' if kid else None))
            sgn = er.choice((-1, 1))
            wp = [lp(S, *c) for c in ((X + sgn * er.uniform(3.5, 5.0), -3.7), (X, -1.0), (X, 0.2), (X + off, 2.4 + 0.5 * (q % 2)))]
            if kid:
                give_balloon(pin)
            go(pin, route(t - dist(wp[:3]) / V, wp), period=12.5 if kid else 25)
        else:
            pout = person("leave_%s_%d" % (S['kind'], q), dress=(prnd.choice(SHIRTS) if (i + q) % 2 else None))
            give_bag(pout)
            wq = [lp(S, *c) for c in ((X + off, 3.1 + 0.4 * (q % 2)), (X, 0.2), (X, -1.0), (X + er.choice((-1, 1)) * 1.6, -3.6))]
            r_ = route(t - dist(wq[:2]) / V, wq)
            r_.append((r_[-1][0] + 40.0 / V, r_[-1][1] + er.choice((-1, 1)) * 40.0, r_[-1][2]))
            go(pout, r_)
        S['door_t'].append(t)


def pacer(name, xa, xb, y, v=V, kid=False, f0=-30, **kw):
    p = person(name, kid=kid, **kw)
    fast = v > V * 1.2
    go(p, shuttle((xa, y), (xb, y), v, f0), period=(12.5 if fast else 25), amp=(0.85 if fast else 0.6), bob=(0.07 if fast else 0.04))
    return p


w = pacer("kidA", -26, -12, -3.5, 0.075, kid=True); give_balloon(w, '#FF5C8A')
w = pacer("adultN2", 22, 8, -3.9); give_bag(w)
pacer("pairN_a", -8, 4, -3.45, 0.05, f0=-60)
w = pacer("pairN_b", -7.2, 4.8, -3.45, 0.05, kid=True, f0=-60); give_balloon(w, '#7FB5FF')
pacer("dogwalker", 22, 12, -3.4, 0.05, f0=-30)
pacer("coupleN_a", -14, -2, -3.8, 0.045)
pacer("coupleN_b", -13.2, -1.2, -3.8, 0.045, dress='#FF9E6B')
w = pacer("adultS1", -24, -8, -14.4); give_bag(w)
w = pacer("kidS_ice", -2, -14, -14.2, 0.05, kid=True); give_cone(w, ['#FFB8CD', '#FFF6E6'])
pacer("adultS2", 26, 14, -14.6, dress='#C8B6F2')
pacer("kidS_a", 8, -4, -14.8, 0.07, kid=True, hat='#FFD166')
pacer("kidS_b", 9.2, -2.8, -14.5, 0.07, kid=True)
pacer("teenS", -8, 6, -14.5, 0.06, hat='#3D8BD9')
w = pacer("adultN3", 6, -6, -4.0, 0.05, hat='#E63946'); give_bag(w)
w = pacer("kidN_ice", 22, 10, -3.6, 0.05, kid=True); give_cone(w, ['#7A4B2A', '#9BE5B5'])
w = pacer("adultN4", -22, -10, -4.0, 0.05); give_bag(w)
pacer("adultS3", 12, 24, -15.0, 0.045)
pacer("adultS4", -22, -6, -15.2, 0.05, hat='#FF9E6B')
w = pacer("kidN_c", 14, 26, -3.4, 0.06, kid=True); give_balloon(w, '#FFD166')
pacer("adultN5", 12, 24, -4.1, 0.05, dress='#7FB5FF')
# crossing the street at the zebra, back and forth
for (name, xo, kid, kw, f0) in (("crossA", 12.4, False, dict(dress='#FF7FA8'), 88), ("crossB", 11.9, True, {}, 90),
                                ("crossC", 12.9, True, dict(hat='#4FC9BE'), 86), ("crossD", 12.9, False, dict(hat='#2F4B5C'), -150)):
    p = person(name, kid=kid, **kw)
    if name == "crossD":
        give_bag(p)
    go(p, shuttle((xo, -4.3), (xo, -14.3), 0.07, f0, pause=70), period=12.5)
# popcorn vendor and two kids waiting
vend = person("vendor", hat='#FFFFFF', shirt='#E63946')
vend['root'].location = (PX, PY + 0.85, 0)
vend['root'].rotation_euler[2] = -math.pi / 2
idle(vend)
for j, (kx, ky) in enumerate(((PX - 0.6, PY - 0.95), (PX + 0.3, PY - 1.0))):
    kk = person("waitkid%d" % j, kid=True, hat=('#FF7FA8' if j else None))
    kk['root'].location = (kx, ky, 0)
    kk['root'].rotation_euler[2] = math.pi / 2
    idle(kk, ph=j, kid=True)
# a kid on the south sidewalk flies a kite
kk = person("kiteKid", kid=True, hat='#FF9E6B')
kk['root'].location = (22.5, -15.8, 0)
kk['root'].rotation_euler[2] = math.radians(-15)
idle(kk, kid=True)
KITE_POS = (31.0, -12.0, 15.0)
rod("kite_string", (22.7, -15.9, 1.15), KITE_POS, 0.01, WHITE)
k0 = len(_new)
box("kite_body", -0.9, 0.9, -0.03, 0.03, -0.9, 0.9, M('#FF5C8A', 0.5), rot=Matrix.Rotation(math.pi / 4, 4, 'Y'))
for t_ in range(6):
    ico("kite_bow", (0.4 * math.sin(t_), 0, -1.5 - t_ * 0.45), 0.12, M(PASTELS[t_ % 7], 0.6))
KITE = empty("kite", (0, 0, 0))
adopt(_new[k0:-1], KITE)
KITE.location = KITE_POS
# a kid on a scooter on the north sidewalk (rides the whole block once)
sk = person("scooterKid", kid=True, hat='#FF5C8A')
for q in (box("scooter_deck", -0.45, 0.3, -0.07, 0.07, 0.1, 0.16, M('#4FC9BE', 0.5)),
          box("scooter_stem", 0.3, 0.34, -0.03, 0.03, 0.12, 1.0, POLE),
          box("scooter_bar", 0.28, 0.36, -0.2, 0.2, 1.0, 1.05, POLE),
          disc("scooter_w1", (-0.4, 0, 0.1), 0.1, 0.05, CHOC2, seg=8, axis='Y'),
          disc("scooter_w2", (0.32, 0, 0.1), 0.1, 0.05, CHOC2, seg=8, axis='Y')):
    child(q, sk['root'])
go(sk, [(-30, -100.0, -3.3), (END + 30, -100.0 + 0.14 * (END + 60), -3.3)], period=12.5, amp=0.0, bob=0.0)


def spinner(builder):
    k0_ = len(_new)
    builder()
    e = empty("spin", (0, 0, 0))
    adopt(_new[k0_:-1], e)
    return e


# a kid on a bike rides along the road
cyc = empty("cyclist", (0, 0, 0))
cyc_p = person("cycleKid", kid=True, hat='#FFD166', shirt='#4FC9BE')
cyc_p['root'].parent = cyc
cyc_p['root'].location = (-0.15, 0, 0.5)
cwheels = []
for wx in (-0.5, 0.5):
    e = spinner(lambda: wheel((0, 0, 0), 0.36, CHOC2, M('#DDE3EA'), 5, 0.05))
    e.parent = cyc
    e.location = (wx, 0, 0.36)
    cwheels.append(e)
bf = M('#FF5C8A', 0.5)
pa, pb, ps, pbb, ph_ = Vector((-0.5, 0, 0.36)), Vector((0.5, 0, 0.36)), Vector((-0.18, 0, 0.9)), Vector((0, 0, 0.32)), Vector((0.38, 0, 0.78))
for p_, q_ in ((pa, ps), (ps, pbb), (pbb, pa), (ps, ph_), (pbb, ph_), (ph_, pb)):
    rod("cyc_frame", p_, q_, 0.015, bf).parent = cyc
box("cyc_seat", -0.3, -0.08, -0.05, 0.05, 0.9, 0.95, CHOC2).parent = cyc
CYC_V = 0.08
go({'root': cyc, 'legs': [], 'arms': []}, [(-30, -60.0, -5.7), (END + 30, -60.0 + CYC_V * (END + 60), -5.7)], bob=0.0)
for e in cwheels:
    kf(e, 'rotation_euler', 1, -30, 0.0, 'LINEAR')
    kf(e, 'rotation_euler', 1, END + 30, -(CYC_V * (END + 60) / 0.36), 'LINEAR')
for f in beat_keys(BEAT / 4):    # one pedal turn per beat (115 rpm)
    for i_, l in enumerate(cyc_p['legs']):
        kf(l, 'rotation_euler', 1, f, 0.8 * math.sin((f - BEAT0) / BEAT * TAU + i_ * math.pi))


def make_dog():
    dog = empty("dog")
    pbox("dog_body", -0.3, 0.3, -0.1, 0.1, 0.25, 0.45, M('#E3A25A'), (0, 0, 0), dog)
    child(ico("dog_head", (0.36, 0, 0.5), 0.12, M('#E3A25A')), dog)
    child(ico("dog_snout", (0.47, 0, 0.47), (0.07, 0.05, 0.05), M('#F6D6A8')), dog)
    child(ico("dog_nose", (0.53, 0, 0.48), 0.025, CHOC2), dog)
    for sy in (-1, 1):
        pbox("dog_ear", 0.30, 0.36, sy * 0.1 - 0.015, sy * 0.1 + 0.015, 0.5, 0.66, M('#9A6A3A'), (0.33, sy * 0.1, 0.62), dog)
    dl = [pbox("dog_leg", lx - 0.035, lx + 0.035, sy * 0.07 - 0.035, sy * 0.07 + 0.035, 0, 0.27, M('#C98A4B'), (lx, sy * 0.07, 0.27), dog)
          for (lx, sy) in ((0.22, 1), (0.22, -1), (-0.22, 1), (-0.22, -1))]
    tail = pbox("dog_tail", -0.5, -0.3, -0.02, 0.02, 0.40, 0.44, M('#C98A4B'), (-0.3, 0, 0.42), dog)
    return dog, dl, tail


dog, dlegs, dtail = make_dog()
go({'root': dog, 'legs': [], 'arms': []}, shuttle((20.4, -3.7), (10.4, -3.7), 0.05, -36), bob=0.0)   # trots just ahead of its owner
for f in beat_keys(BEAT / 8):    # two trot strides per beat, the tail wags four times per beat
    a = 0.7 * math.sin((f - BEAT0) / (BEAT / 2) * TAU)
    for i_, l in enumerate(dlegs):
        kf(l, 'rotation_euler', 1, f, a * (1 if i_ in (0, 3) else -1))
    kf(dtail, 'rotation_euler', 2, f, 0.6 * math.sin((f - BEAT0) / (BEAT / 4) * TAU))

# (walk version: the street is closed to cars on Saturday morning, so no driving cars)

# ======================================================================
# Animation of the street itself
# ======================================================================
for S in SHOP_LIST:   # doors: open 20 frames before a shopper reaches them, close 28 frames after
    h, base = S['hinge'], S['hinge_base']
    merged = []
    for a, b in sorted((t - 20, t + 28) for t in S['door_t']):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    kf(h, 'rotation_euler', 2, -30, base)
    for a, b in merged:
        kf(h, 'rotation_euler', 2, a, base)
        kf(h, 'rotation_euler', 2, a + 14, base + 1.3)
        kf(h, 'rotation_euler', 2, b - 14, base + 1.3)
        kf(h, 'rotation_euler', 2, b, base)
for S in SHOP_LIST:   # emblem on the wall
    rig, mode = S['emb']
    b0 = tuple(rig.rotation_euler)
    for f in beat_keys(6.25):
        if mode == 'roll':
            kf(rig, 'rotation_euler', 1, f, math.radians(1.5 * f))
        elif mode == 'sway':
            kf(rig, 'rotation_euler', 2, f, b0[2] + 0.18 * PF * math.sin((f - BEAT0) / (4 * BEAT) * TAU))
        else:
            v_ = 1.0 + 0.07 * PF * math.sin((f - BEAT0) / (2 * BEAT) * TAU)
            kf(rig, 'scale', None, f, (v_, v_, v_))
for (fo, k, rz) in FLAGS:
    for f in beat_keys(BEAT / 4):
        kf(fo, 'rotation_euler', 0, f, 0.28 * PF * math.sin((f - BEAT0) / (2 * BEAT) * TAU + k * 0.9))
        kf(fo, 'rotation_euler', 1, f, 0.12 * PF * math.sin((f - BEAT0) / (3 * BEAT) * TAU + k * 0.5))
for k, rig in enumerate(TREES):
    for f in range(-8, FRAMES + 10, 6):
        kf(rig, 'rotation_euler', 1, f, 0.05 * math.sin(f / 48 * TAU + k))
        kf(rig, 'rotation_euler', 0, f, 0.03 * math.sin(f / 36 * TAU + k))
for k, cr in enumerate(CLOUD_RIGS):
    kf(cr, 'location', 1, -10, 0.0, 'LINEAR')
    kf(cr, 'location', 1, FRAMES + 10, 6.0 + 2 * k, 'LINEAR')
for i, m_ in enumerate(BULB_M):   # string lights: a soft ripple along the string, one wave per beat
    for f in beat_keys(BEAT / 4):
        kf_socket(m_, 'Emission Strength', f, 3.0 + 1.2 * math.cos((f - BEAT0) / BEAT * TAU - i * TAU / 3))
for (sm, neon, _kind) in SIGN_MATS:   # signs: unchanged slow breathing / neon flicker (a glow tied to the notes was invisible in daylight, so it was dropped)
    for f in range(-8, FRAMES + 10, 6):
        v_ = (5.0 + (-3.0 if (f % 36) in (12, 18) else 0.5 * math.sin(f / 9))) if neon else 0.35 + 0.8 * (0.5 + 0.5 * math.sin(f / 36 * TAU))
        kf_socket(sm, 'Emission Strength', f, v_, 'LINEAR')
for (b_o, wings, k) in BIRDS:
    for (f, x, y, z) in ((-10, 200 + 9 * k, -40 - 14 * k, 26 + 3 * k), (FRAMES + 10, -60 + 9 * k, -20 - 14 * k, 34 + 3 * k)):
        kf(b_o, 'location', 0, f, x, 'LINEAR')
        kf(b_o, 'location', 1, f, y, 'LINEAR')
        kf(b_o, 'location', 2, f, z, 'LINEAR')
    kf(b_o, 'rotation_euler', 2, -10, math.pi, 'LINEAR')
    for f in range(-10, FRAMES + 12, 3):
        for i_, w_ in enumerate(wings):
            kf(w_, 'rotation_euler', 0, f, (0.7 if ((f // 3 + k) % 2) else -0.5) * (1 if i_ == 0 else -1), 'BEZIER')
SMK = M('#FFFFFF', 1.0, emit='#F0F0F8', strength=0.6)   # chimney smoke
for S in SHOP_LIST:
    if not S.get('chimney'):
        continue
    bx, by = lp(S, 3.75, 3.95)
    for i in range(6):
        pf = ico("smoke", (bx, by, S['H'] + 2.4), 1.0, SMK, shadow=False)
        for c in range(-1, 17):
            for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                fr_ = i * 10 + c * 60 + t * 60 + (1 if t == 0.0 else 0)
                if fr_ < -2 or fr_ > FRAMES + 8:
                    continue
                kf(pf, 'location', 0, fr_, bx + 0.7 * math.sin(t * 3.0 + i), 'LINEAR')
                kf(pf, 'location', 2, fr_, S['H'] + 2.4 + t * 4.2, 'LINEAR')
                sz = 0.001 if t in (0.0, 1.0) else 0.18 + 0.45 * math.sin(math.pi * t)
                kf(pf, 'scale', None, fr_, (sz, sz, sz), 'BEZIER')

# ======================================================================
# Lights, world, camera, render
# ======================================================================
sun = add_light("morning_sun", 'SUN', (0, -9, 30), 2.6, '#FFDDB0')
sun.data.angle = math.radians(4.0)
sun.rotation_euler = (-SUN_DIR).to_track_quat('-Z', 'Y').to_euler()
world = bpy.data.worlds.new("dusk")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (*srgb('#CFE4F7'), 1)
bg.inputs[1].default_value = 0.85
scene.world = world

cam_d = bpy.data.cameras.new("cam")
cam_d.lens = 26
cam_d.clip_end = 2000
cam = bpy.data.objects.new("Camera", cam_d)
scene.collection.objects.link(cam)
scene.camera = cam
target = empty("cam_target", (0, 0, 0))
tc_ = cam.constraints.new('TRACK_TO')
tc_.target, tc_.track_axis, tc_.up_axis = target, 'TRACK_NEGATIVE_Z', 'UP_Y'
cam_d.lens = LENS
cam_d.keyframe_insert('lens', frame=1)
_MID = FRAMES // 2                                  # cruise speed here: 0.05 m per frame
_STEP = (CAM_X[_MID] - CAM_X[_MID - 1]) * BEAT      # 0.625 m: one step per beat
_FB = BEAT0 + BEAT * round((_MID - BEAT0) / BEAT)   # a beat frame near the middle of the walk
_XB = CAM_X[_MID - 1] + (CAM_X[_MID] - CAM_X[_MID - 1]) * (_FB - _MID)
for i_ in range(FRAMES):
    f_ = i_ + 1
    x_ = CAM_X[i_]
    psi_ = psi_of(x_)
    y_ = Y_MID + Y_AMP * max(-1.0, min(1.0, psi_ / PSI_SECOND)) + 0.012 * PUNCH * math.sin(TAU * (x_ - _XB) / (2 * _STEP))   # weight shift
    z_ = CAM_Z - 0.010 * PUNCH * math.cos(TAU * (x_ - _XB) / _STEP)     # one small bob per step; the head is lowest when a foot lands, on the beat; stops when the walker stops
    loc_ = (x_, y_, z_)
    tgt_ = (x_ + 40 * math.cos(psi_) * math.cos(PITCH), y_ + 40 * math.sin(psi_) * math.cos(PITCH), z_ + 40 * math.sin(PITCH))
    for k_ in range(3):
        kf(cam, 'location', k_, f_, loc_[k_], 'LINEAR')
        kf(target, 'location', k_, f_, tgt_[k_], 'LINEAR')

# name tags: parented to the camera, scale 0 when not shown; each shop gets one while the walker looks at it
for si, t0 in VIEW_T.items():
    S = SHOP_LIST[si]
    rig = empty("tag_" + S['kind'], (0, 0, 0))
    rig.parent = cam
    rig.location = (-1.18, -0.82, -3.0)
    box("tag_back", -0.95, 0.95, -0.2, 0.2, -0.04, -0.01, M('#FFF1D8', 0.5, emit='#FFF1D8', strength=0.9)).parent = rig
    box("tag_bar", -0.95, -0.88, -0.2, 0.2, -0.01, 0.01, M(S['acc'], 0.5, emit=S['acc'], strength=0.9)).parent = rig
    tx = text(S['text'], (0.04, 0, 0.01), 0.2, M('#4A2A1C', 0.5, emit='#4A2A1C', strength=0.2), rot=(0, 0, 0), extrude=0.0, maxw=1.7)
    tx.parent = rig
    for (f, v_) in ((1, 0.0), (t0 - 44, 0.0), (t0 - 34, 1.0), (t0 + 34, 1.0), (t0 + 44, 0.0), (FRAMES, 0.0)):
        kf(rig, 'scale', None, f, (0.5 * v_, 0.5 * v_, 0.5 * v_), 'BEZIER')

if BEATS:   # one timeline marker per bar (visible in Blender's timeline, not in the video)
    for b_ in BEATS['bars']:
        scene.timeline_markers.new(b_['name'], frame=round(b_['start']))

# ---- optional effects: one module per file (fx_<name>.py), run with this script's globals (scene, cam, SHOP_LIST, VIEW_T, BEATS, kf, person, ...).
# WALK_FX=a,b limits the list; WALK_FX= (empty) turns every effect off.
for _n in [n for n in os.environ.get('WALK_FX', 'notes,dancers,bunting,shafts,moments,react,finale').split(',') if n]:
    _p = os.path.join(OUT, 'fx_%s.py' % _n)
    if os.path.exists(_p):
        exec(compile(open(_p, encoding='utf-8').read(), _p, 'exec'), globals())
        print('FX loaded', _n)
    else:
        print('FX missing', _n)

r = scene.render
for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
    try:
        r.engine = eng
        break
    except TypeError:
        pass
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, PERCENT
scene.view_settings.view_transform = 'Standard'
try:
    scene.eevee.taa_render_samples = 32
    scene.eevee.shadow_pool_size = '1024'
except Exception:
    pass
blend = os.path.join(OUT, TAG + ".blend")
bpy.ops.wm.save_as_mainfile(filepath=blend)
if MODE == 'anim':   # PNG sequence (safe to resume); encode with ffmpeg afterwards
    if len(ARGS) > 2:
        scene.frame_start, scene.frame_end = int(ARGS[1]), int(ARGS[2])
    r.image_settings.file_format = 'PNG'
    r.use_overwrite = False
    r.use_placeholder = True
    os.makedirs(os.path.join(OUT, TAG + "_frames"), exist_ok=True)
    r.filepath = os.path.join(OUT, TAG + "_frames", "f_")
    bpy.ops.render.render(animation=True)
elif MODE == 'save':
    pass
else:
    r.image_settings.file_format = 'PNG'
    scene.frame_set(STILL_FRAME)
    r.filepath = os.path.join(OUT, TAG + ".png")
    bpy.ops.render.render(write_still=True)
print("OK", blend, "mode:", MODE, "objects:", len(bpy.data.objects), "engine:", r.engine)
