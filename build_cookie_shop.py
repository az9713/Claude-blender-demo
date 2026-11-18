"""v2: night scene + tables/chairs/pots + detail + camera orbit animation.
Run: blender.exe -b -P build_cookie_shop.py -- still   (frame 60 -> cookie_shop_night.png)
     blender.exe -b -P build_cookie_shop.py -- anim    (120 frames -> Desktop/CookieShop.mp4)
Z up, metres. Storefront faces -Y."""
import bpy, bmesh, math, os, random, sys
from mathutils import Matrix, Vector

OUT = os.path.dirname(os.path.abspath(__file__))
MODE = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else 'still'
DESKTOP = os.path.join(os.environ['USERPROFILE'], 'Desktop')
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


# ---------- helpers ----------
def srgb(h):
    h = h.lstrip('#')
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b))


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
            mp = nt.nodes.new('ShaderNodeMapping')   # stand bricks up on the front face
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
    o.location = loc
    scene.collection.objects.link(o)
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


def ico(name, c, s, m, sub=1, shadow=True):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
    sx, sy, sz = (s, s, s) if isinstance(s, (int, float)) else s
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    return build(name, bm, m, loc=c, shadow=shadow)


def cookie(name, c, r, h, axis, dough, chip, nchips=8, seed=1, sprinkles=False):
    """Faceted cookie. axis 'Y' = standing, front face toward -Y. axis 'Z' = lying flat."""
    disc(name, c, r, h, dough, seg=12, axis=axis, jit=0.04, seed=seed)
    # slightly smaller, lighter-edged top plate gives a baked crown
    rim = M('#C98A4B') if dough != M('#C98A4B') else M('#B07038')
    ang0 = seed * 1.3
    for k in range(nchips):
        a = k * 2.399 + ang0
        rad = r * 0.72 * math.sqrt((k + 0.5) / nchips)
        u, v = math.cos(a) * rad, math.sin(a) * rad
        sz = r * (0.13 if not sprinkles else 0.07) * (0.85 + 0.3 * ((k * 7) % 5) / 4)
        if axis == 'Y':
            pos = (c[0] + u, c[1] - h / 2, c[2] + v)
            s = (sz, sz * 0.55, sz)
        else:
            pos = (c[0] + u, c[1] + v, c[2] + h / 2)
            s = (sz, sz, sz * 0.55)
        ico(name + "_chip", pos, s, chip)


def cupcake(c, wrap, frost, cherry=True):
    disc("cc_wrap", (c[0], c[1], c[2] + 0.08), 0.12, 0.16, wrap, seg=8, taper=1.35)
    ico("cc_frost", (c[0], c[1], c[2] + 0.21), (0.16, 0.16, 0.12), frost)
    if cherry:
        ico("cc_cherry", (c[0], c[1], c[2] + 0.33), 0.045, M('#E63946'))


def frame(x0, x1, z0, z1, m, t=0.15, y0=-0.12, y1=0.4):
    box("fr_l", x0 - t, x0, y0, y1, z0 - t, z1 + t, m)
    box("fr_r", x1, x1 + t, y0, y1, z0 - t, z1 + t, m)
    box("fr_b", x0 - t, x1 + t, y0 - 0.06, y1, z0 - t, z0, m)
    box("fr_t", x0 - t, x1 + t, y0, y1, z1, z1 + t, m)


def to_track(o, target):
    d = Vector(target) - o.location
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


# ---------- palette ----------
PINK = M('#F8B4CB', 0.9, bump=(45, 0.25))
MINT = M('#A6E3CF', 0.85, brick=(6.0, '#92D9C3', '#E9F7F0'))
CREAM = M('#FFF1D8')
LAV = M('#C8B6F2')
CHOC = M('#4A2A1C', 0.7)
DOUGH = M('#E3A25A', 0.9, bump=(14, 0.7))
DOUGH_D = M('#6B3E26', 0.9)
CHIP = M('#4B2A1E', 0.8)
FROST = M('#FF8FB5', 0.7)
BROWN_DOOR = M('#B9743F', 0.75)
GOLD = M('#FFD166', 0.35)
GLASS = M('#FFD9A0', 0.05, emit='#FFB45C', strength=1.0, alpha=0.30)   # night: warm glowing glass
GLASS_DARK = M('#1B2450', 0.1, alpha=0.6)
GLOW_GLASS = M('#FFE2A8', 0.3, emit='#FFC76B', strength=2.0)
WARM_BULB = M('#FFE7B0', 0.4, emit='#FFC070', strength=14)
STRIPE_A = M('#4FC9BE', 0.8, bump=(220, 0.12))
STRIPE_B = M('#FFF6E6', 0.8, bump=(220, 0.12))
SIDEWALK = M('#EFE6EE', 0.95, bump=(30, 0.3))
TILE_VAR = [SIDEWALK, M('#E6DCE8', 0.95, bump=(30, 0.3)), M('#F3EAF0', 0.95, bump=(30, 0.3))]
SIDEWALK_G = M('#C6BBC9', 0.95)

# ---------- ground ----------
box("grass", -90, 90, -35, 90, -0.6, -0.1, M('#B7E9B2'))
box("street", -90, 90, -35, -5.0, -0.3, -0.02, M('#8E8CA8', 0.95))
for i in range(-9, 10):
    box("lane", i * 3.2 - 0.8, i * 3.2 + 0.8, -15.1, -14.9, -0.03, 0.005, CREAM)
box("curb", -15, 15, -5.0, -4.55, 0.0, 0.2, M('#F6DDE4'))
box("walk_base", -15, 15, -4.55, 0.0, 0.0, 0.12, SIDEWALK_G)
for ix in range(20):
    for iy in range(3):
        x0 = -15 + ix * 1.5
        y0 = -4.5 + iy * 1.5
        box("tile", x0 + 0.03, x0 + 1.47, y0 + 0.03, y0 + 1.47, 0.12, 0.15, TILE_VAR[(ix * 7 + iy * 3) % 3])

# ---------- shop shell ----------
H = 7.6
box("floor_slab", -5, 5, 0, 6, 0, 0.15, CREAM)
box("wall_left", -5, -4.6, 0.4, 6, 0.15, H, PINK)
box("wall_right", 4.6, 5, 0.4, 6, 0.15, H, PINK)
box("wall_back", -5, 5, 5.6, 6, 0.15, H, PINK)
box("upper_block", -5, 5, 0.4, 6, 3.4, H, PINK)
# front wall, pink, 0.4 thick, openings for 2 windows (z 0.8..2.7) and the door (z up to 2.4)
box("pillar_L", -5.0, -4.6, 0, 0.4, 0.8, H, PINK)
box("pillar_M1", -1.6, -0.9, 0, 0.4, 0.8, H, PINK)
box("pillar_M2", 0.9, 1.6, 0, 0.4, 0.8, H, PINK)
box("pillar_R", 4.6, 5.0, 0, 0.4, 0.8, H, PINK)
box("hdr_winL", -4.6, -1.6, 0, 0.4, 2.7, H, PINK)
box("hdr_winR", 1.6, 4.6, 0, 0.4, 2.7, H, PINK)
box("hdr_door", -0.9, 0.9, 0, 0.4, 2.4, H, PINK)
box("base_L", -5.0, -0.9, -0.05, 0.4, 0, 0.8, MINT)
box("base_R", 0.9, 5.0, -0.05, 0.4, 0, 0.8, MINT)
box("base_cap_L", -5.05, -0.9, -0.12, 0.0, 0.7, 0.8, CREAM)
box("base_cap_R", 0.9, 5.05, -0.12, 0.0, 0.7, 0.8, CREAM)
# cornice
box("cornice", -5.3, 5.3, -0.35, 6.3, H, H + 0.4, LAV)
box("cornice_band", -5.12, 5.12, -0.14, 0.0, H - 0.3, H, CREAM)
for i in range(-9, 10, 1):   # little tooth trim on the cornice
    box("tooth", i * 0.55 - 0.18, i * 0.55 + 0.18, -0.42, -0.35, H + 0.1, H + 0.3, CREAM)

# windows: trim + glass + mullions
for (x0, x1) in ((-4.6, -1.6), (1.6, 4.6)):
    frame(x0, x1, 0.8, 2.7, CREAM)
    box("glass", x0, x1, 0.18, 0.24, 0.8, 2.7, GLASS, shadow=False)
    xm = (x0 + x1) / 2
    box("mullion_v", xm - 0.04, xm + 0.04, -0.02, 0.28, 0.8, 2.7, CREAM)
    box("mullion_h", x0, x1, -0.02, 0.28, 1.75, 1.83, CREAM)
# upper little windows (lit)
for (x0, x1) in ((-4.25, -2.95), (2.95, 4.25)):
    frame(x0, x1, 5.2, 6.6, CREAM, t=0.12)
    box("up_glass", x0, x1, -0.04, 0.0, 5.2, 6.6, GLOW_GLASS)
    xm = (x0 + x1) / 2
    box("up_mull_v", xm - 0.03, xm + 0.03, -0.02, 0.12, 5.2, 6.6, CREAM)
    box("up_mull_h", x0, x1, -0.02, 0.12, 5.87, 5.93, CREAM)
    box("up_planter", x0 - 0.15, x1 + 0.15, -0.5, 0.0, 4.95, 5.2, MINT)
    for k in range(4):
        ico("up_flower", (x0 + 0.15 + k * (x1 - x0 - 0.3) / 3, -0.25, 5.3), 0.13,
            [M('#FF7FA8'), M('#FFD166'), M('#FFFFFF'), M('#FF7FA8')][k])

# door
frame(-0.9, 0.9, 0.15, 2.4, CREAM)
box("door_low", -0.85, 0.85, 0.08, 0.22, 0.15, 1.0, BROWN_DOOR)
box("door_stile_L", -0.85, -0.6, 0.08, 0.22, 1.0, 2.35, BROWN_DOOR)
box("door_stile_R", 0.6, 0.85, 0.08, 0.22, 1.0, 2.35, BROWN_DOOR)
box("door_rail", -0.85, 0.85, 0.08, 0.22, 2.1, 2.35, BROWN_DOOR)
box("door_glass", -0.6, 0.6, 0.13, 0.17, 1.0, 2.1, GLASS, shadow=False)
ico("door_knob", (0.72, 0.03, 1.05), 0.065, GOLD)
box("doormat", -0.8, 0.8, -0.95, -0.12, 0.15, 0.19, M('#E8707F'))
box("step", -1.05, 1.05, -0.3, 0.0, 0.0, 0.3, CREAM)

# ---------- awning ----------
n = 10
x_left, x_right = -5.25, 5.25
w = (x_right - x_left) / n
phi = math.atan2(0.6, 1.3)
L = math.hypot(1.3, 0.6)
for i in range(n):
    xa, xb = x_left + i * w, x_left + (i + 1) * w
    m = STRIPE_A if i % 2 == 0 else STRIPE_B
    rot = Matrix.Translation((0, -0.65, 3.3)) @ Matrix.Rotation(phi, 4, 'X')
    box("awning_stripe", xa, xb, -L / 2, L / 2, -0.03, 0.03, m, rot=rot)
    # scalloped valance: triangle prism hanging from the front edge
    bm = bmesh.new()
    yf = -1.3
    tri = [(xa, yf, 3.0), (xb, yf, 3.0), ((xa + xb) / 2, yf, 2.62)]
    f1 = [bm.verts.new(p) for p in tri]
    f2 = [bm.verts.new((p[0], p[1] + 0.06, p[2])) for p in tri]
    bm.faces.new(f1)
    bm.faces.new(f2[::-1])
    for k in range(3):
        j = (k + 1) % 3
        bm.faces.new([f1[k], f1[j], f2[j], f2[k]])
    build("awning_valance", bm, m)
# awning side cheeks and wall rail
for sx in (x_left, x_right):
    bm = bmesh.new()
    p = [(sx, 0.0, 3.6), (sx, -1.3, 3.0), (sx, 0.0, 3.0)]
    a = [bm.verts.new(q) for q in p]
    b = [bm.verts.new((q[0] + 0.05 * (1 if sx > 0 else -1), q[1], q[2])) for q in p]
    bm.faces.new(a)
    bm.faces.new(b[::-1])
    for k in range(3):
        j = (k + 1) % 3
        bm.faces.new([a[k], a[j], b[j], b[k]])
    build("awning_cheek", bm, STRIPE_B)

# ---------- sign ----------
box("sign_rim", -3.6, 3.6, -0.22, 0.0, 3.8, 4.8, CREAM)
box("sign_board", -3.5, 3.5, -0.3, -0.18, 3.9, 4.7, CHOC)
for sx in (-3.0, 3.0):
    cookie("sign_cookie", (sx, -0.4, 4.3), 0.26, 0.08, 'Y', DOUGH, CHIP, nchips=4, seed=3)
font = None
for fp in (r"C:\Windows\Fonts\comicbd.ttf", r"C:\Windows\Fonts\ARLRDBD.TTF", r"C:\Windows\Fonts\arialbd.ttf"):
    if os.path.exists(fp):
        font = bpy.data.fonts.load(fp)
        break
cu = bpy.data.curves.new("sign_text", 'FONT')
cu.body = "Kevin Cookie Company"
cu.align_x = 'CENTER'
cu.align_y = 'CENTER'
cu.size = 0.68
cu.extrude = 0.04
if font:
    cu.font = font
SIGN_M = M('#FFD7E4', 0.5, emit='#FFB3CB', strength=0.35)
cu.materials.append(SIGN_M)
txt = bpy.data.objects.new("sign_text", cu)
txt.location = (0, -0.33, 4.3)
txt.rotation_euler = (math.pi / 2, 0, 0)
scene.collection.objects.link(txt)
bpy.context.view_layer.update()
if txt.dimensions.x > 5.2:
    s = 5.2 / txt.dimensions.x
    txt.scale = (s, s, s)

# ---------- giant cookie over the entrance ----------
CK = (0.0, -0.3, 6.05)
n_cookie0 = len(scene.collection.objects)
disc("giant_cookie", CK, 0.98, 0.42, DOUGH, seg=12, axis='Y', jit=0.04, seed=5)
# lighter crown plate on the face, then chips on the crown
disc("giant_crown", (CK[0], CK[1] - 0.2, CK[2]), 0.8, 0.05, M('#EDB46E', 0.9), seg=12, axis='Y', jit=0.05, seed=9)
for k in range(11):
    a = k * 2.399 + 0.7
    rad = 0.72 * math.sqrt((k + 0.5) / 11)
    sz = 0.13 * (0.85 + 0.3 * ((k * 7) % 5) / 4)
    ico("giant_chip", (CK[0] + math.cos(a) * rad, CK[1] - 0.25, CK[2] + math.sin(a) * rad),
        (sz, sz * 0.55, sz), CHIP)
# extra texture: small chocolate chunks, crumbs, sugar specks, bumpy rim
rnd = random.Random(42)
for k in range(16):
    a = rnd.uniform(0, 2 * math.pi); rad = 0.78 * math.sqrt(rnd.random())
    sz = rnd.uniform(0.035, 0.07)
    ico("giant_crumb", (CK[0] + math.cos(a) * rad, CK[1] - 0.24, CK[2] + math.sin(a) * rad),
        (sz, sz * 0.5, sz), M('#6B3E26', 0.8))
for k in range(30):
    a = rnd.uniform(0, 2 * math.pi); rad = 0.8 * math.sqrt(rnd.random())
    ico("giant_sugar", (CK[0] + math.cos(a) * rad, CK[1] - 0.235, CK[2] + math.sin(a) * rad),
        (0.018, 0.01, 0.018), M('#FFFFFF', 0.4, emit='#FFFFFF', strength=0.4))
for k in range(12):
    a = 2 * math.pi * k / 12 + 0.2
    ico("giant_rim", (CK[0] + math.cos(a) * 0.93, CK[1] - 0.12, CK[2] + math.sin(a) * 0.93),
        (0.11, 0.2, 0.11), M('#C98A4B', 0.9))
cookie_parts = list(scene.collection.objects)[n_cookie0:]
cookie_rig = bpy.data.objects.new("cookie_rig", None)
cookie_rig.location = CK
scene.collection.objects.link(cookie_rig)
bpy.context.view_layer.update()
for o in cookie_parts:
    o.parent = cookie_rig
    o.matrix_parent_inverse = cookie_rig.matrix_world.inverted()
box("cookie_bracket_L", -0.12, 0.12, -0.2, 0.0, 5.0, 5.35, CHOC)
box("cookie_bracket_R", -0.12, 0.12, -0.2, 0.0, 6.75, 7.1, CHOC)
# a halo of little hearts / stars around the cookie: low-poly sprinkles on the wall
for k, (dx, dz, col) in enumerate(((-1.55, 6.9, '#FF7FA8'), (1.6, 6.6, '#FFD166'), (-1.7, 5.2, '#4FC9BE'),
                                     (1.45, 5.15, '#C8B6F2'), (-2.2, 6.2, '#FFD166'), (2.2, 6.05, '#FF7FA8'))):
    ico("sparkle", (dx, -0.12, dz), 0.1, M(col, 0.5))

# ---------- interior ----------
for ix in range(9):
    for iy in range(5):
        col = M('#FFB8CD') if (ix + iy) % 2 == 0 else M('#FFF6E6')
        box("ftile", -4.5 + ix, -3.5 + ix, 0.45 + iy, 1.45 + iy, 0.15, 0.19, col)
box("back_panel", -4.6, 4.6, 5.52, 5.6, 0.19, 3.4, M('#FFF3E0'))
# shelves with jars
for zs in (1.3, 2.0, 2.7):
    box("shelf", -4.5, 4.5, 5.0, 5.52, zs, zs + 0.06, M('#C98A5B'))
    for k in range(-4, 5):
        col = [M('#FF8FB5'), M('#A6E3CF'), M('#FFD166'), M('#C8B6F2')][(k + int(zs * 3)) % 4]
        disc("jar", (k * 1.0, 5.25, zs + 0.2), 0.2, 0.28, col, seg=8)
        disc("jar_lid", (k * 1.0, 5.25, zs + 0.38), 0.14, 0.08, M('#FFFFFF'), seg=8)
# counter
box("counter", -3.0, 3.0, 3.8, 4.7, 0.19, 1.05, PINK)
box("counter_top", -3.1, 3.1, 3.7, 4.8, 1.05, 1.12, CREAM)
for k, x in enumerate((-2.2, -0.8, 0.6, 1.9)):
    disc("plate", (x, 4.25, 1.15), 0.32, 0.04, M('#FFFFFF'), seg=10)
    cookie("counter_cookie", (x, 4.25, 1.2), 0.26, 0.07, 'Z', DOUGH if k % 2 == 0 else DOUGH_D,
           CHIP if k % 2 == 0 else M('#FFF1D8'), nchips=5, seed=k + 20)
# pendant lights
for (x, y) in ((-3.0, 2.0), (3.0, 2.0), (0.0, 3.2)):
    box("cord", x - 0.01, x + 0.01, y - 0.01, y + 0.01, 2.95, 3.4, CHOC)
    ico("bulb", (x, y, 2.8), 0.2, WARM_BULB, shadow=False)

# window displays
for (x0, x1, kind) in ((-4.4, -1.8, 'cookies'), (1.8, 4.4, 'tower')):
    box("disp_table", x0, x1, 0.55, 1.75, 0.19, 0.72, MINT)
    box("disp_top", x0 - 0.05, x1 + 0.05, 0.5, 1.8, 0.72, 0.78, CREAM)
    xm = (x0 + x1) / 2
    if kind == 'cookies':
        for k, (dx, dough, chip) in enumerate(((-0.8, DOUGH, CHIP), (0.0, DOUGH_D, M('#FFF1D8')), (0.8, M('#FFA3C0'), M('#FFFFFF')))):
            for t in range(3):
                cookie("stack", (xm + dx + 0.03 * ((t * 3) % 2), 1.2, 0.84 + t * 0.09), 0.3, 0.08, 'Z',
                       dough, chip, nchips=5, seed=k * 5 + t, sprinkles=(k == 2))
    else:
        for (zp, r) in ((0.95, 0.85), (1.55, 0.6), (2.05, 0.38)):
            disc("tier", (xm, 1.2, zp), r, 0.05, M('#FFFFFF'), seg=12)
        for (zp0, zp1) in ((0.78, 0.95), (0.95, 1.55), (1.55, 2.05)):
            disc("pole", (xm, 1.2, (zp0 + zp1) / 2), 0.04, zp1 - zp0, GOLD, seg=6)
        for k in range(6):
            a = k * math.pi / 3
            cupcake((xm + math.cos(a) * 0.55, 1.2 + math.sin(a) * 0.55, 0.975),
                    [M('#4FC9BE'), M('#FFD166'), M('#C8B6F2')][k % 3],
                    [FROST, M('#FFFFFF'), M('#FFD7A8')][k % 3])
        for k in range(3):
            a = k * 2 * math.pi / 3 + 0.5
            cupcake((xm + math.cos(a) * 0.32, 1.2 + math.sin(a) * 0.32, 1.575), M('#FF7FA8'), M('#FFFFFF'))
        cookie("tower_top", (xm, 1.2, 2.2), 0.24, 0.08, 'Z', DOUGH, CHIP, nchips=5, seed=11)

# ---------- street dressing ----------
# flower pots beside the door
for sx in (-1.25, 1.25):
    disc("pot", (sx, -0.45, 0.4), 0.22, 0.5, M('#E07A5F'), seg=8, taper=1.25)
    for k, col in enumerate(('#FF7FA8', '#FFD166', '#FFFFFF', '#FF7FA8')):
        ico("pot_flower", (sx + (k - 1.5) * 0.1, -0.45 + (0.06 if k % 2 else -0.06), 0.78 + 0.05 * (k % 2)), 0.1, M(col, 0.6))
    ico("pot_leaf", (sx, -0.45, 0.68), (0.22, 0.22, 0.12), M('#58C27D'))
# lollipop trees
for (x, canopy) in ((-6.3, '#9BE5B5'), (6.3, '#FFC49B')):
    box("planter", x - 0.5, x + 0.5, -3.5, -2.5, 0.15, 0.55, MINT)
    disc("trunk", (x, -3.0, 1.45), 0.09, 1.8, M('#B7835A'), seg=6)
    ico("canopy", (x, -3.0, 3.0), (1.0, 1.0, 0.95), M(canopy, 0.9), sub=1)
    ico("canopy_hi", (x - 0.35, -3.35, 3.35), (0.4, 0.4, 0.35), M('#FFFFFF', 0.9), sub=1)
# street lamps
for x in (-8.5, 8.5):
    disc("lamp_base", (x, -4.2, 0.35), 0.16, 0.4, M('#3D5A6C'), seg=8, taper=0.8)
    disc("lamp_pole", (x, -4.2, 2.0), 0.06, 3.5, M('#3D5A6C'), seg=6)
    ico("lamp_head", (x, -4.2, 3.9), 0.3, M('#FFE7B0', 0.4, emit='#FFC070', strength=10), shadow=False)
    disc("lamp_cap", (x, -4.2, 4.25), 0.22, 0.06, M('#3D5A6C'), seg=8, taper=0.5)
# neighbours
def neighbour(x0, x1, h, col, wcol_hex):
    body = M(col)
    box("nb_body", x0, x1, 0, 6, 0, h, body)
    box("nb_cornice", x0 - 0.1, x1 + 0.1, -0.2, 6.1, h, h + 0.3, CREAM)
    box("nb_base", x0, x1, -0.05, 0.1, 0, 0.7, CREAM)
    cx = [x0 + (x1 - x0) * f for f in (0.2, 0.5, 0.8)]
    for rowz, tall in ((1.0, 1.7), (3.9, 1.5)):
        for x in cx:
            frame(x - 0.75, x + 0.75, rowz, rowz + tall, CREAM, t=0.12, y0=-0.1, y1=0.05)
            box("nb_glass", x - 0.75, x + 0.75, -0.05, 0.0, rowz, rowz + tall,
                GLOW_GLASS if rowz > 3 else GLASS_DARK, shadow=False)
neighbour(-14.5, -5.0, 6.4, '#FFE9A8', None)
neighbour(5.0, 14.5, 5.7, '#CFC2F5', None)

# clouds (each cloud is parented to an empty so it can drift)
CLOUD_RIGS = []
for (cx, cy, cz, sc) in ((-8, 14, 10.5, 1.0), (7, 16, 11.5, 1.2)):
    n_c0 = len(scene.collection.objects)
    for k, (dx, dz, s_) in enumerate(((0, 0, 1.4), (1.5, 0.2, 1.1), (-1.5, -0.1, 1.0), (0.6, 0.7, 0.9))):
        ico("cloud", (cx + dx * sc, cy, cz + dz * sc), (s_ * sc * 1.4, s_ * sc, s_ * sc * 0.8), M('#8E9BC8', 1.0, emit='#7C89BA', strength=0.25))
    rig_c = bpy.data.objects.new("cloud_rig", None)
    scene.collection.objects.link(rig_c)
    for o in list(scene.collection.objects)[n_c0:-1]:
        o.parent = rig_c
    CLOUD_RIGS.append(rig_c)

# ---------- v2 additions: tables, chairs, pots ----------
def chair(cx, cy, phi, seat_hex, leg_hex):
    ang = phi + math.pi / 2
    R = Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(ang, 4, 'Z')
    sm, lm = M(seat_hex, 0.7), M(leg_hex, 0.7)
    for lx in (-0.17, 0.17):
        for ly in (-0.17, 0.17):
            box("chair_leg", lx - 0.02, lx + 0.02, ly - 0.02, ly + 0.02, 0.15, 0.6, lm, rot=R)
    box("chair_seat", -0.21, 0.21, -0.21, 0.21, 0.6, 0.66, sm, rot=R)
    box("chair_back", -0.21, 0.21, -0.23, -0.19, 0.66, 1.15, sm, rot=R)
    box("chair_slat", -0.15, 0.15, -0.235, -0.185, 0.78, 0.95, lm, rot=R)

def table(tx, ty, top_hex, chair_hex, leg_hex, phis):
    disc("table_base", (tx, ty, 0.17), 0.28, 0.04, M(leg_hex, 0.6), seg=10)
    disc("table_pole", (tx, ty, 0.55), 0.05, 0.76, M(leg_hex, 0.6), seg=6)
    disc("table_top", (tx, ty, 0.94), 0.56, 0.06, M(top_hex, 0.6), seg=12)
    disc("table_rim", (tx, ty, 0.915), 0.585, 0.03, M(leg_hex, 0.6), seg=12)
    for phi in phis:
        chair(tx + 0.9 * math.cos(phi), ty + 0.9 * math.sin(phi), phi, chair_hex, leg_hex)
    # plate + cookie, flower vase, glowing candle lantern
    disc("plate", (tx - 0.15, ty - 0.1, 0.98), 0.19, 0.02, M('#FFFFFF'), seg=10)
    cookie("table_cookie", (tx - 0.15, ty - 0.1, 1.02), 0.14, 0.05, 'Z', DOUGH, CHIP, nchips=3, seed=int(tx * 10) % 7)
    disc("vase", (tx + 0.22, ty + 0.12, 1.04), 0.05, 0.16, M('#A6E3CF'), seg=6)
    for k, col in enumerate(('#FF7FA8', '#FFD166', '#FFFFFF')):
        ico("vase_flower", (tx + 0.22 + (k - 1) * 0.045, ty + 0.12, 1.16 + 0.02 * (k % 2)), 0.045, M(col, 0.6))
    disc("lantern", (tx + 0.3, ty - 0.2, 1.0), 0.05, 0.1, WARM_BULB, seg=6)
    disc("lantern_cap", (tx + 0.3, ty - 0.2, 1.065), 0.06, 0.03, M('#3D5A6C'), seg=6)

table(-3.4, -2.4, '#FF9EBB', '#4FC9BE', '#3D5A6C', (math.radians(200), math.radians(340)))
table(3.4, -2.4, '#FFD166', '#C8B6F2', '#3D5A6C', (math.radians(200), math.radians(340)))

# more colourful flower pots near the entrance (the two terracotta pots stay as they were)
for (px, hexp, h, flowers) in ((-1.95, '#FFD166', 0.55, ('#FF7FA8', '#FFFFFF', '#C8B6F2')),
                                (-2.6, '#C8B6F2', 0.4, ('#FFD166', '#FF7FA8', '#FFD166')),
                                (1.95, '#4FC9BE', 0.55, ('#FFD166', '#FF9E6B', '#FFFFFF')),
                                (2.6, '#FF7FA8', 0.4, ('#C8B6F2', '#FFFFFF', '#FFD166'))):
    disc("pot2", (px, -0.5, 0.15 + h / 2), 0.2, h, M(hexp, 0.7), seg=8, taper=1.25)
    ico("pot2_leaf", (px, -0.5, 0.15 + h + 0.03), (0.24, 0.24, 0.12), M('#58C27D'))
    for k, col in enumerate(flowers):
        ico("pot2_flower", (px + (k - 1) * 0.12, -0.5 + (0.06 if k % 2 else -0.06), 0.15 + h + 0.15 + 0.04 * (k % 2)), 0.09, M(col, 0.6))

# ---------- v2 additions: extra storefront / awning / sidewalk detail ----------
# raised panels on the mint base under the windows
for (x0, x1) in ((-4.4, -1.8), (1.8, 4.4)):
    for (a, b, c, d) in ((x0, x1, 0.2, 0.26), (x0, x1, 0.6, 0.66)):
        box("panel_h", a, b, -0.1, -0.05, c, d, CREAM)
    for xx in (x0, x1 - 0.06):
        box("panel_v", xx, xx + 0.06, -0.1, -0.05, 0.2, 0.66, CREAM)
box("door_kickplate", -0.85, 0.85, 0.04, 0.08, 0.15, 0.4, GOLD)
# awning: piping along the front edge, ribs between stripes, gold tassels on the valance points
box("awning_piping", x_left, x_right, -1.34, -1.28, 2.97, 3.05, M('#FFF6E6', 0.6))
for i in range(n + 1):
    xr = x_left + i * w
    rot = Matrix.Translation((0, -0.65, 3.3 + 0.04)) @ Matrix.Rotation(phi, 4, 'X')
    box("awning_rib", xr - 0.015, xr + 0.015, -L / 2, L / 2, -0.03, 0.03, M('#E8DCC4', 0.7), rot=rot)
for i in range(n):
    xm = x_left + (i + 0.5) * w
    ico("awning_tassel", (xm, -1.27, 2.57), 0.055, GOLD)
# festoon bulbs along the awning front edge
BULB_M = [M('#FFE7B0', 0.4, emit='#FFC070', strength=14 + i * 0.01) for i in range(3)]
for k in range(21):
    xb = -5.0 + k * 0.5
    ico("festoon_bulb", (xb, -1.38, 3.04 - 0.04 * math.sin(math.pi * (k % 2))), 0.07, BULB_M[k % 3], shadow=False)
# wall sconces beside the door
for sx in (-1.25, 1.25):
    box("sconce_arm", sx - 0.03, sx + 0.03, -0.2, 0.0, 1.95, 2.0, M('#3D5A6C'))
    ico("sconce_lamp", (sx, -0.25, 2.02), 0.1, WARM_BULB, shadow=False)
# sidewalk: cracks, gum, crumbs, leaves
rnd = random.Random(7)
for k in range(14):
    cx_, cy_ = rnd.uniform(-9, 9), rnd.uniform(-4.2, -0.5)
    a = rnd.uniform(0, math.pi)
    rot = Matrix.Translation((cx_, cy_, 0)) @ Matrix.Rotation(a, 4, 'Z')
    box("crack", -rnd.uniform(0.25, 0.6), rnd.uniform(0.25, 0.6), -0.012, 0.012, 0.15, 0.153, M('#9C90A0', 0.9), rot=rot)
for k in range(10):
    disc("gum", (rnd.uniform(-9, 9), rnd.uniform(-4.2, -0.6), 0.152), 0.05, 0.006, M('#FF9EBB', 0.5), seg=7)
for k in range(30):
    sz = rnd.uniform(0.02, 0.045)
    ico("crumb", (rnd.uniform(-7, 7), rnd.uniform(-4.2, -0.5), 0.16), (sz, sz, sz * 0.6), M('#C98A4B', 0.9))
for k in range(8):
    disc("leaf", (rnd.uniform(-9, 9), rnd.uniform(-4.2, -0.6), 0.153), 0.09, 0.004, M(['#F4A261', '#E9C46A', '#E76F51'][k % 3], 0.9), seg=5)

# ---------- v2 additions: night sky ----------
STAR_M = [M('#FFFFFF', 0.5, emit='#FFFFFF', strength=6 + i * 0.01) for i in range(3)]
rnd = random.Random(3)
for k in range(260):
    az = math.radians(rnd.uniform(-70, 70))
    el = math.radians(rnd.uniform(2, 24))
    R_ = 80
    ico("star", (R_ * math.sin(az) * math.cos(el), R_ * math.cos(az) * math.cos(el), 4 + R_ * math.sin(el)),
        rnd.uniform(0.1, 0.22), STAR_M[k % 3], shadow=False)
MOON_M = M('#FFF3C4', 0.6, emit='#FFF0B0', strength=2.2)
ico("moon", (-14, 70, 21), 2.6, MOON_M, sub=2, shadow=False)

# ---------- lights ----------
def add_light(name, kind, loc, energy, hexcol, size=0.3):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = srgb(hexcol)
    if kind == 'POINT':
        ld.shadow_soft_size = size
    o = bpy.data.objects.new(name, ld)
    o.location = loc
    scene.collection.objects.link(o)
    return o


sun_dir = Vector((0.45, 0.7, -0.62)).to_track_quat('-Z', 'Y').to_euler()
moon_l = add_light("moonlight", 'SUN', (0, -10, 12), 0.75, '#8FA8FF')
moon_l.data.angle = math.radians(3)
moon_l.rotation_euler = sun_dir
# warm light inside the shop
for (x, y) in ((-3.0, 2.0), (3.0, 2.0), (0.0, 3.2)):
    add_light("warm_in", 'POINT', (x, y, 2.6), 450, '#FFB566', 0.25)
add_light("warm_counter", 'POINT', (0, 4.2, 2.2), 200, '#FFB566', 0.3)
# soft exterior light on the storefront
g = add_light("glow_sign", 'AREA', (0, -3.5, 4.4), 260, '#FFC98A', 3)
to_track(g, (0, 0, 4.3))
for x in (-3.0, 0.0, 3.0):
    add_light("awning_glow", 'POINT', (x, -1.0, 2.7), 90, '#FFC070', 0.4)
for sx in (-1.25, 1.25):
    add_light("sconce_light", 'POINT', (sx, -0.4, 2.0), 40, '#FFC070', 0.15)


def add_spot(name, loc, target, energy, hexcol, size_deg, blend=0.6):
    ld = bpy.data.lights.new(name, 'SPOT')
    ld.energy = energy
    ld.color = srgb(hexcol)
    ld.spot_size = math.radians(size_deg)
    ld.spot_blend = blend
    ld.shadow_soft_size = 0.2
    o = bpy.data.objects.new(name, ld)
    o.location = loc
    scene.collection.objects.link(o)
    to_track(o, target)
    return o

add_spot("cookie_spot", (0, -5.0, 2.6), (0, -0.3, 6.0), 700, '#FFC98A', 38)
for x in (-8.5, 8.5):
    add_spot("lamp_spot", (x, -4.2, 3.8), (x, -3.0, 0.0), 700, '#FFC070', 110, 0.8)
fill = add_light("sky_fill", 'AREA', (-6, -14, 6), 60, '#8FA8FF', 8)
to_track(fill, (0, 0, 3.5))

# world: deep blue night sky
world = bpy.data.worlds.new("sky")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (*srgb('#1A2766'), 1)
bg.inputs[1].default_value = 0.35
scene.world = world

# ---------- camera + 5 s orbit animation ----------
cam_d = bpy.data.cameras.new("cam")
cam_d.lens = 50
cam = bpy.data.objects.new("Camera", cam_d)
cam.location = (3.7, -27.0, 4.8)
scene.collection.objects.link(cam)
to_track(cam, (0.0, 0.0, 3.9))
scene.camera = cam
cam_rig = bpy.data.objects.new("camera_orbit", None)   # sits on the Z axis through the shop, so the shop stays centred
scene.collection.objects.link(cam_rig)
cam.parent = cam_rig

FPS, SECONDS = 24, 5
scene.render.fps, scene.render.fps_base = FPS, 1.0
scene.frame_start, scene.frame_end = 1, FPS * SECONDS
bpy.context.preferences.edit.keyframe_new_interpolation_type = 'BEZIER'
base_az = math.degrees(math.atan2(3.7, 27.0))
cam_rig.rotation_euler = (0, 0, math.radians(-30 - base_az))
cam_rig.keyframe_insert('rotation_euler', index=2, frame=1)
cam_rig.rotation_euler = (0, 0, math.radians(30 - base_az))
cam_rig.keyframe_insert('rotation_euler', index=2, frame=FPS * SECONDS)
bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
cookie_rig.rotation_euler = (0, 0, 0)
cookie_rig.keyframe_insert('rotation_euler', index=1, frame=1)
cookie_rig.rotation_euler = (0, math.radians(180), 0)
cookie_rig.keyframe_insert('rotation_euler', index=1, frame=FPS * SECONDS)
scene.frame_set(1)


# =====================================================================
# v3: more detail + a lively street (all motion is keyframed)
# =====================================================================
FRAMES = scene.frame_end
TAU = math.tau
bpy.context.view_layer.update()


def kf(o, path, idx, f, val, kind='BEZIER'):
    bpy.context.preferences.edit.keyframe_new_interpolation_type = kind
    if idx is None:
        setattr(o, path, val)
        o.keyframe_insert(path, frame=f)
    else:
        getattr(o, path)[idx] = val
        o.keyframe_insert(path, index=idx, frame=f)


def kf_socket(mat, name, f, val, kind='BEZIER'):
    bpy.context.preferences.edit.keyframe_new_interpolation_type = kind
    sk = mat.node_tree.nodes["Principled BSDF"].inputs[name]
    sk.default_value = val
    sk.keyframe_insert('default_value', frame=f)


def empty(name, loc=(0, 0, 0), rot=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    e.rotation_euler = rot
    scene.collection.objects.link(e)
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


def rod(name, p0, p1, r, m):
    a, b = Vector(p0), Vector(p1)
    d = b - a
    rot = Matrix.Translation((a + b) / 2) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    return box(name, -r, r, -r, r, -d.length / 2, d.length / 2, m, rot=rot, shadow=False)


# ---------- extra static detail ----------
BRICK = M('#C96B5A', 0.9, brick=(7.0, '#B85C4C', '#E8D9C8'))
box("chimney", 3.3, 4.2, 3.5, 4.4, H + 0.3, H + 2.0, BRICK)
box("chimney_cap", 3.2, 4.3, 3.4, 4.5, H + 2.0, H + 2.2, LAV)

# chalkboard A-frame sign on the sidewalk
for sgn, yb in ((-1, -1.5), (1, -1.2)):
    rot = Matrix.Translation((-2.3, yb, 0.15)) @ Matrix.Rotation(sgn * math.radians(10), 4, 'X')
    box("chalk_panel", -0.32, 0.32, -0.025, 0.025, 0.0, 0.9, M('#2F3B45', 0.9) if sgn < 0 else CHOC, rot=rot)
box("chalk_top", -0.35, 0.35, -1.42, -1.28, 1.0, 1.04, CHOC)
cu2 = bpy.data.curves.new("chalk_text", 'FONT')
cu2.body = "Fresh\nCookies!"
cu2.align_x = 'CENTER'
cu2.align_y = 'CENTER'
cu2.size = 0.14
cu2.extrude = 0.004
if font:
    cu2.font = font
cu2.materials.append(M('#FFF6E6', 0.6, emit='#FFF6E6', strength=0.5))
chalk = bpy.data.objects.new("chalk_text", cu2)
chalk.location = (-2.3, -1.43, 0.72)
chalk.rotation_euler = (math.pi / 2 - 0.1745, 0, 0)
scene.collection.objects.link(chalk)

# pink hydrant and a mint bin on the sidewalk
disc("hydrant", (-5.6, -0.6, 0.45), 0.14, 0.6, M('#FF7FA8', 0.6), seg=8)
ico("hydrant_dome", (-5.6, -0.6, 0.78), (0.15, 0.15, 0.12), M('#FF7FA8', 0.6))
box("hydrant_nub", -5.78, -5.42, -0.64, -0.56, 0.5, 0.58, M('#FFD166'))
disc("bin", (5.6, -0.6, 0.5), 0.26, 0.7, MINT, seg=8, taper=1.1)
disc("bin_lid", (5.6, -0.6, 0.88), 0.29, 0.06, M('#4FC9BE'), seg=8)

# bunting swags on the facade
FLAG_COL = ['#FF7FA8', '#FFD166', '#4FC9BE', '#C8B6F2', '#FF9E6B']
flags = []
for (xa, xb) in ((-4.8, -1.4), (1.4, 4.8)):
    pts = []
    for k in range(9):
        t = k / 8
        pts.append((xa + (xb - xa) * t, -0.22, 7.42 - 0.32 * math.sin(math.pi * t)))
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
        fo = build("flag", bm, M(FLAG_COL[(k + int(xa)) % 5], 0.8), loc=(x_, y_ - 0.01, z_))
        flags.append((fo, k))

# OPEN sign on the door glass
cu3 = bpy.data.curves.new("open_text", 'FONT')
cu3.body = "OPEN"
cu3.align_x = 'CENTER'
cu3.align_y = 'CENTER'
cu3.size = 0.2
cu3.extrude = 0.01
if font:
    cu3.font = font
OPEN_M = M('#FF5C8A', 0.4, emit='#FF5C8A', strength=5)
cu3.materials.append(OPEN_M)
open_sign = bpy.data.objects.new("door_open_sign", cu3)
open_sign.location = (0, 0.03, 1.55)
open_sign.rotation_euler = (math.pi / 2, 0, 0)
scene.collection.objects.link(open_sign)

# ---------- characters ----------
def person(name, shirt, pants, skin='#F2C6A0', hair='#4B2E24', s_=1.0):
    root = empty(name)
    root.scale = (s_, s_, s_)
    pbox("torso", -0.13, 0.13, -0.21, 0.21, 0.55, 1.1, M(shirt), (0, 0, 0), root)
    pbox("hips", -0.12, 0.12, -0.17, 0.17, 0.5, 0.6, M(pants), (0, 0, 0), root)
    child(ico(name + "_head", (0, 0, 1.3), 0.17, M(skin)), root)
    child(ico(name + "_hair", (-0.02, 0, 1.4), (0.18, 0.18, 0.11), M(hair)), root)
    for sy in (-1, 1):
        child(ico(name + "_eye", (0.15, sy * 0.06, 1.32), 0.03, M('#2B2B33')), root)
    child(ico(name + "_nose", (0.17, 0, 1.28), 0.03, M(skin)), root)
    legs, arms = [], []
    for sy in (1, -1):
        legs.append(pbox("leg", -0.07, 0.07, sy * 0.1 - 0.06, sy * 0.1 + 0.06, 0, 0.55, M(pants), (0, sy * 0.1, 0.55), root))
        a = pbox("arm", -0.05, 0.05, sy * 0.26 - 0.05, sy * 0.26 + 0.05, 0.62, 1.05, M(shirt), (0, sy * 0.26, 1.05), root)
        child(ico(name + "_hand", (0, 0, -0.45), 0.06, M(skin)), a)
        arms.append(a)
    return {'root': root, 'legs': legs, 'arms': arms}


def walk(p, f0, f1, period=16, amp=0.6, bob=0.04, base_z=0.0):
    f = f0
    while f <= f1 + 0.01:
        ph = (f - f0) / period * TAU
        a = amp * math.sin(ph)
        for i, l in enumerate(p['legs']):
            kf(l, 'rotation_euler', 1, f, a * (1 if i == 0 else -1))
        for i, ar in enumerate(p['arms']):
            kf(ar, 'rotation_euler', 1, f, -a * 0.8 * (1 if i == 0 else -1))
        kf(p['root'], 'location', 2, f, base_z + abs(math.sin(ph)) * bob)
        f += period / 4


def rest(p, f):
    for l in p['legs'] + p['arms']:
        kf(l, 'rotation_euler', 1, f, 0.0)


def path(root, pts, rot_z=None):
    for (f, x, y) in pts:
        kf(root, 'location', 0, f, x, 'LINEAR')
        kf(root, 'location', 1, f, y, 'LINEAR')


# A: a kid with a balloon, jogging left to right
A = person("kidA", '#FF7FA8', '#3D5A6C', s_=0.8)
kf(A['root'], 'rotation_euler', 2, 1, 0.0, 'LINEAR')
path(A['root'], [(1, -10.5, -4.15), (FRAMES + 1, 9.5, -4.15)])
walk(A, 1, FRAMES + 1, period=10, amp=0.8, bob=0.07)
bal = ico("balloon", (0.0, 0.3, 2.55), (0.27, 0.27, 0.33), M('#FF5C8A', 0.25))
child(bal, A['root'])
string = box("balloon_string", -0.006, 0.006, 0.294, 0.306, 0.7, 2.25, M('#FFFFFF'), shadow=False)
child(string, A['root'])
for f in range(1, FRAMES + 2, 6):
    kf(bal, 'location', 2, f, 2.55 + 0.1 * math.sin(f / 18 * TAU))
    kf(bal, 'rotation_euler', 1, f, -0.35 + 0.1 * math.sin(f / 12 * TAU))

# dog trotting behind kid A
dog = empty("dog")
pbox("dog_body", -0.3, 0.3, -0.1, 0.1, 0.25, 0.45, M('#E3A25A'), (0, 0, 0), dog)
child(ico("dog_head", (0.36, 0, 0.5), 0.12, M('#E3A25A')), dog)
child(ico("dog_snout", (0.47, 0, 0.47), (0.07, 0.05, 0.05), M('#F6D6A8')), dog)
child(ico("dog_nose", (0.53, 0, 0.48), 0.025, M('#2B2B33')), dog)
for sy in (-1, 1):
    pbox("dog_ear", 0.30, 0.36, sy * 0.1 - 0.015, sy * 0.1 + 0.015, 0.5, 0.66, M('#9A6A3A'), (0.33, sy * 0.1, 0.62), dog)
dog_legs = []
for (lx, sy) in ((0.22, 1), (0.22, -1), (-0.22, 1), (-0.22, -1)):
    dog_legs.append(pbox("dog_leg", lx - 0.035, lx + 0.035, sy * 0.07 - 0.035, sy * 0.07 + 0.035, 0, 0.27, M('#C98A4B'), (lx, sy * 0.07, 0.27), dog))
tail = pbox("dog_tail", -0.5, -0.3, -0.02, 0.02, 0.40, 0.44, M('#C98A4B'), (-0.3, 0, 0.42), dog)
kf(dog, 'rotation_euler', 2, 1, 0.0, 'LINEAR')
path(dog, [(1, -12.0, -3.8), (FRAMES + 1, 8.0, -3.8)])
f = 1.0
while f <= FRAMES + 1:
    a = 0.7 * math.sin((f - 1) / 7 * TAU)
    for i, l in enumerate(dog_legs):
        kf(l, 'rotation_euler', 1, f, a * (1 if i in (0, 3) else -1))
    kf(dog, 'location', 2, f, abs(math.sin((f - 1) / 7 * TAU)) * 0.05)
    kf(tail, 'rotation_euler', 2, f, 0.6 * math.sin((f - 1) / 3.5 * TAU))
    f += 1.75

# C: a walker going the other way
C = person("walkerC", '#4FC9BE', '#C8B6F2', skin='#8D5B3A', hair='#1F1B1A')
kf(C['root'], 'rotation_euler', 2, 1, math.pi, 'LINEAR')
path(C['root'], [(1, 9.5, -4.4), (FRAMES + 1, -9.5, -4.4)])
walk(C, 1, FRAMES + 1, period=14, amp=0.65, bob=0.05)

# B: a customer who walks up, the door opens, and she goes inside
B = person("customerB", '#FFD166', '#3D5A6C', skin='#F2C6A0', hair='#C98A4B')
ang1 = math.atan2(-1.0 + 4.2, 0.25 - 2.0)
kf(B['root'], 'rotation_euler', 2, 1, ang1, 'LINEAR')
kf(B['root'], 'rotation_euler', 2, 46, ang1, 'BEZIER')
kf(B['root'], 'rotation_euler', 2, 54, math.pi / 2, 'BEZIER')
path(B['root'], [(1, 2.0, -4.2), (46, 0.25, -1.0), (54, 0.25, -1.0), (84, 0.25, 3.0), (FRAMES + 1, 0.25, 3.0)])
walk(B, 1, 46, period=16, amp=0.6, bob=0.04)
rest(B, 50)
kf(B['root'], 'location', 2, 50, 0.0)
walk(B, 54, 84, period=16, amp=0.6, bob=0.04)
rest(B, 88)
kf(B['root'], 'location', 2, 88, 0.0)
# she is inside the shop at the end, so she stays lit and visible through the glass

# the door swings on a hinge: open for B
door_objs = [o for o in scene.collection.objects if o.name.startswith('door_') and o.parent is None]
hinge = empty("hinge_empty", (-0.85, 0.15, 0.0))
adopt(door_objs, hinge)
kf(hinge, 'rotation_euler', 2, 1, 0.0)
kf(hinge, 'rotation_euler', 2, 40, 0.0)
kf(hinge, 'rotation_euler', 2, 52, 1.3)
kf(hinge, 'rotation_euler', 2, 84, 1.3)
kf(hinge, 'rotation_euler', 2, 98, 0.0)
for f in range(1, FRAMES + 2, 3):   # the OPEN neon buzzes
    kf_socket(OPEN_M, 'Emission Strength', f, 5.0 if (f % 24) not in (9, 12, 15) else 1.5, 'LINEAR')

# a car drives down the street, wheels spinning, headlights on
car = empty("car")
body_m = M('#FFD166', 0.5)
pbox("car_body", -1.6, 1.6, -0.75, 0.75, 0.35, 0.85, body_m, (0, 0, 0), car)
pbox("car_cabin", -0.7, 0.9, -0.65, 0.65, 0.85, 1.35, M('#CFEFFF', 0.2), (0, 0, 0), car)
pbox("car_roof", -0.8, 1.0, -0.7, 0.7, 1.35, 1.42, body_m, (0, 0, 0), car)
pbox("car_bumper", 1.55, 1.7, -0.7, 0.7, 0.3, 0.45, M('#FFF6E6'), (0, 0, 0), car)
for sy in (-1, 1):
    child(ico("car_light", (1.62, sy * 0.5, 0.65), (0.08, 0.14, 0.1), M('#FFF3C4', 0.3, emit='#FFE9A0', strength=12), shadow=False), car)
    child(ico("car_tail", (-1.62, sy * 0.5, 0.65), (0.05, 0.12, 0.08), M('#FF5C5C', 0.3, emit='#FF3030', strength=4), shadow=False), car)
wheels = []
for (wx, sy) in ((1.0, 1), (1.0, -1), (-1.0, 1), (-1.0, -1)):
    w = disc("car_wheel", (0, 0, 0), 0.35, 0.2, M('#2B2B33', 0.9), seg=10, axis='Y')
    w.location = (wx, sy * 0.78, 0.35)
    w.parent = car
    hub = disc("car_hub", (0, sy * 0.11, 0), 0.16, 0.04, M('#FFF6E6'), seg=8, axis='Y')
    hub.parent = w
    wheels.append(w)
spot_car = bpy.data.lights.new("car_headlight", 'SPOT')
spot_car.energy = 900
spot_car.color = srgb('#FFE9A8')
spot_car.spot_size = math.radians(70)
spot_car.spot_blend = 0.7
sc_o = bpy.data.objects.new("car_headlight", spot_car)
scene.collection.objects.link(sc_o)
sc_o.parent = car
sc_o.location = (1.7, 0, 0.6)
sc_o.rotation_euler = (0, -math.pi / 2 + 0.12, 0)
kf(car, 'rotation_euler', 2, 1, 0.0, 'LINEAR')
path(car, [(1, -24.0, -12.0), (FRAMES + 1, 24.0, -12.0)])
for w in wheels:
    kf(w, 'rotation_euler', 1, 1, 0.0, 'LINEAR')
    kf(w, 'rotation_euler', 1, FRAMES + 1, -(48.0 / 0.35), 'LINEAR')
for f in range(1, FRAMES + 2, 3):
    kf(car, 'location', 2, f, 0.03 * math.sin(f / 4 * TAU))

# ---------- the cat, the pigeons ----------
cat = empty("cat", (-2.2, -0.1, 4.8))
FUR = M('#F2994A', 0.9)
child(ico("cat_body", (0, 0, 0.17), (0.14, 0.2, 0.17), FUR), cat)
child(ico("cat_chest", (0, -0.1, 0.17), (0.09, 0.08, 0.12), M('#FFF6E6')), cat)
child(ico("cat_head", (0, -0.12, 0.4), (0.12, 0.11, 0.1), FUR), cat)
ears = []
for sx in (-1, 1):
    ears.append(pbox("cat_ear", sx * 0.07 - 0.025, sx * 0.07 + 0.025, -0.13, -0.11, 0.48, 0.56, FUR, (sx * 0.07, -0.12, 0.48), cat))
    child(ico("cat_eye", (sx * 0.045, -0.225, 0.42), 0.02, M('#9BE5B5', 0.3, emit='#9BE5B5', strength=2)), cat)
ctail = pbox("cat_tail", 0.12, 0.42, 0.08, 0.12, 0.06, 0.11, FUR, (0.12, 0.1, 0.06), cat)
for f in range(1, FRAMES + 2, 4):
    kf(ctail, 'rotation_euler', 2, f, 0.55 * math.sin(f / 32 * TAU))
    kf(cat, 'rotation_euler', 2, f, 0.08 * math.sin(f / 60 * TAU))
for f in (1, 30, 33, 36, 80, 83, 86, 121):
    kf(ears[0], 'rotation_euler', 1, f, 0.35 if f in (33, 83) else 0.0)


def pigeon(name, x, y, z, flying=False):
    pg = empty(name, (x, y, z), (0, 0, math.pi))
    child(ico(name + "_body", (0, 0, 0.14), (0.2, 0.12, 0.13), M('#8D96B5', 0.9)), pg)
    head = child(ico(name + "_head", (0.19, 0, 0.27), 0.075, M('#6E789B', 0.9)), pg)
    child(ico(name + "_beak", (0.27, 0, 0.26), (0.04, 0.02, 0.02), M('#FF9E6B')), pg)
    child(ico(name + "_neck", (0.12, 0, 0.2), (0.07, 0.08, 0.1), M('#7FD6C4', 0.5)), pg)
    wings = []
    if flying:
        for sy in (1, -1):
            wings.append(pbox(name + "_wing", -0.12, 0.12, sy * 0.1, sy * 0.4, 0.19, 0.21, M('#7C86A8', 0.9), (0, sy * 0.1, 0.2), pg))
    return pg, head, wings


for k, (px, py) in enumerate(((-3.8, 0.4), (2.4, 0.3), (1.9, 0.6))):
    pg, head, _ = pigeon("pigeon%d" % k, px, py, H + 0.4)
    for f in range(1, FRAMES + 2, 6):
        kf(head, 'location', 0, f, 0.19 + (0.03 if (f // 6 + k) % 2 else 0.0))
pgf, headf, wf = pigeon("pigeonFly", -3.1, 0.5, H + 0.4, flying=True)
for i, w in enumerate(wf):
    kf(w, 'rotation_euler', 0, 1, -1.4 if i == 0 else 1.4, 'LINEAR')
    kf(w, 'rotation_euler', 0, 56, -1.4 if i == 0 else 1.4, 'LINEAR')
    for k in range(0, 9):
        fr_ = 58 + k * 4
        up = (k % 2 == 0)
        kf(w, 'rotation_euler', 0, fr_, (0.9 if up else -0.7) * (1 if i == 0 else -1), 'BEZIER')
fly = [(1, -3.1, 0.5, H + 0.4), (57, -3.1, 0.5, H + 0.4), (66, -3.9, -0.2, H + 1.2), (82, -6.5, -3.0, H + 3.6), (104, -12.0, -8.0, H + 6.5), (FRAMES + 1, -14.0, -9.0, H + 7.0)]
for (f, x, y, z) in fly:
    kf(pgf, 'location', 0, f, x, 'BEZIER')
    kf(pgf, 'location', 1, f, y, 'BEZIER')
    kf(pgf, 'location', 2, f, z, 'BEZIER')
kf(pgf, 'rotation_euler', 1, 57, 0.0)
kf(pgf, 'rotation_euler', 1, 70, 0.45)
kf(pgf, 'rotation_euler', 1, FRAMES + 1, 0.3)

# ---------- chimney smoke: puffs that rise, grow and shrink ----------
SMK = M('#E8E4F0', 1.0, emit='#9AA6D6', strength=0.2)
for i in range(6):
    pf = ico("smoke", (3.75, 3.95, H + 2.4), 1.0, SMK, shadow=False)
    for c in (-1, 0, 1, 2):
        base = i * 10 + c * 60
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            fr_ = base + t * 60 + (1 if t == 0.0 else 0)
            if fr_ < -2 or fr_ > FRAMES + 8:
                continue
            kf(pf, 'location', 0, fr_, 3.75 + 0.7 * math.sin(t * 3.0 + i), 'LINEAR')
            kf(pf, 'location', 2, fr_, H + 2.4 + t * 4.2, 'LINEAR')
            sz = 0.001 if t in (0.0, 1.0) else 0.18 + 0.45 * math.sin(math.pi * t)
            kf(pf, 'scale', None, fr_, (sz, sz, sz), 'BEZIER')

# ---------- trees sway, clouds drift, tassels swing, sparkles pulse ----------
for x_t, ph in ((-6.3, 0.0), (6.3, 1.7)):
    rig = empty("tree_rig", (x_t, -3.0, 2.2))
    kids = [o for o in scene.collection.objects if o.name.startswith('canopy') and abs(o.location.x - x_t) < 1.0 and o.parent is None]
    adopt(kids, rig)
    for f in range(1, FRAMES + 2, 6):
        kf(rig, 'rotation_euler', 1, f, 0.05 * math.sin(f / 48 * TAU + ph))
        kf(rig, 'rotation_euler', 0, f, 0.03 * math.sin(f / 36 * TAU + ph))
for k, cr in enumerate(CLOUD_RIGS):
    kf(cr, 'location', 0, 1, 0.0, 'LINEAR')
    kf(cr, 'location', 0, FRAMES + 1, 5.0 + 2 * k, 'LINEAR')
for k, o in enumerate([o for o in scene.collection.objects if o.name.startswith('awning_tassel')]):
    x0_ = o.location.x
    for f in range(1, FRAMES + 2, 6):
        kf(o, 'location', 0, f, x0_ + 0.05 * math.sin(f / 24 * TAU + k * 0.7))
for k, o in enumerate([o for o in scene.collection.objects if o.name.startswith('sparkle')]):
    for f in range(1, FRAMES + 2, 6):
        v_ = 1.0 + 0.7 * max(0.0, math.sin(f / 30 * TAU + k * 1.1))
        kf(o, 'scale', None, f, (v_, v_, v_))
for (fo, k) in flags:
    for f in range(1, FRAMES + 2, 4):
        kf(fo, 'rotation_euler', 0, f, 0.28 * math.sin(f / 24 * TAU + k * 0.9))
        kf(fo, 'rotation_euler', 1, f, 0.12 * math.sin(f / 30 * TAU + k * 0.5))

# the giant cookie bobs while it spins
for f in range(1, FRAMES + 2, 6):
    kf(cookie_rig, 'location', 2, f, CK[2] + 0.08 * math.sin(f / 48 * TAU))
    kf(cookie_rig, 'rotation_euler', 0, f, 0.06 * math.sin(f / 60 * TAU))

# ---------- lights that breathe ----------
for i, m_ in enumerate(STAR_M):
    for f in range(1, FRAMES + 2, 6):
        kf_socket(m_, 'Emission Strength', f, 1.2 + 5.5 * (0.5 + 0.5 * math.sin(f / 24 * TAU + i * 2.1)))
for i, m_ in enumerate(BULB_M):
    for f in range(1, FRAMES + 2, 2):
        kf_socket(m_, 'Emission Strength', f, 16.0 if ((f // 4) + i) % 3 == 0 else 3.0, 'LINEAR')
for f in range(1, FRAMES + 2, 6):
    kf_socket(SIGN_M, 'Emission Strength', f, 0.35 + 0.9 * (0.5 + 0.5 * math.sin(f / 36 * TAU)))
    kf_socket(MOON_M, 'Emission Strength', f, 2.2 + 0.4 * math.sin(f / 60 * TAU))
for k, o in enumerate([o for o in scene.collection.objects if o.name.startswith('lamp_spot')]):
    rr = random.Random(k)
    for f in range(1, FRAMES + 2, 3):
        o.data.energy = 700 + (rr.uniform(-160, 40) if k == 0 else 20 * math.sin(f / 12 * TAU))
        o.data.keyframe_insert('energy', frame=f)

# shooting star
ss = ico("shooting_star", (28, 70, 22), (2.4, 0.12, 0.12), M('#FFFFFF', 0.4, emit='#FFFFFF', strength=18), shadow=False)
ss.rotation_euler = (0, 2.88, 0)
for (f, v_) in ((1, 0.0), (29, 0.0), (31, 1.0), (51, 1.0), (53, 0.0), (FRAMES + 1, 0.0)):
    kf(ss, 'scale', None, f, (v_ * 2.4 + 1e-4, 0.12, 0.12), 'LINEAR')
kf(ss, 'location', 0, 30, 28.0, 'LINEAR')
kf(ss, 'location', 2, 30, 22.0, 'LINEAR')
kf(ss, 'location', 0, 52, -2.0, 'LINEAR')
kf(ss, 'location', 2, 52, 14.0, 'LINEAR')

# fireflies drifting over the sidewalk and street
FF = [M('#E9FF7A', 0.4, emit='#E9FF7A', strength=8 + i * 0.01) for i in range(3)]
rr = random.Random(11)
for k in range(18):
    pos0 = [rr.uniform(-11, 11), rr.uniform(-8, -1.6), rr.uniform(0.6, 3.6)]
    fo = ico("firefly", tuple(pos0), 0.045, FF[k % 3], shadow=False)
    for f in range(1, FRAMES + 2, 12):
        kf(fo, 'location', 0, f, pos0[0] + rr.uniform(-0.6, 0.6))
        kf(fo, 'location', 1, f, pos0[1] + rr.uniform(-0.5, 0.5))
        kf(fo, 'location', 2, f, pos0[2] + rr.uniform(-0.4, 0.4))
for i, m_ in enumerate(FF):
    for f in range(1, FRAMES + 2, 4):
        kf_socket(m_, 'Emission Strength', f, 1.0 + 9.0 * max(0.0, math.sin(f / 18 * TAU + i * 2.0)))

# a little handheld life in the camera
for f in range(1, FRAMES + 2, 6):
    kf(cam, 'location', 2, f, 4.8 + 0.07 * math.sin(f / 30 * TAU))
    kf(cam, 'location', 0, f, 3.7 + 0.05 * math.sin(f / 42 * TAU))
scene.frame_set(1)

# ---------- render ----------
r = scene.render
for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
    try:
        r.engine = eng
        break
    except TypeError:
        pass
r.resolution_x, r.resolution_y, r.resolution_percentage = 1920, 1080, 100
scene.view_settings.view_transform = 'Standard'
try:
    scene.eevee.taa_render_samples = 48
    scene.eevee.shadow_pool_size = '1024'
except Exception:
    pass

blend = os.path.join(OUT, "cookie_shop_night.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend)
if MODE == 'anim':
    r.image_settings.media_type = 'VIDEO'   # Blender 5.x: pick video before the FFMPEG container
    r.image_settings.file_format = 'FFMPEG'
    r.ffmpeg.format = 'MPEG4'
    r.ffmpeg.codec = 'H264'
    r.ffmpeg.constant_rate_factor = 'MEDIUM'
    r.ffmpeg.ffmpeg_preset = 'GOOD'
    r.ffmpeg.audio_codec = 'NONE'
    r.filepath = os.path.join(OUT, "CookieShop.mp4")
    bpy.ops.render.render(animation=True)
else:
    r.image_settings.file_format = 'PNG'
    scene.frame_set(int(sys.argv[sys.argv.index('--') + 2]) if len(sys.argv) > sys.argv.index('--') + 2 else 60)
    r.filepath = os.path.join(OUT, "cookie_shop_night.png")
    bpy.ops.render.render(write_still=True)
print("OK", blend, "mode:", MODE, "objects:", len(bpy.data.objects), "engine:", r.engine)
