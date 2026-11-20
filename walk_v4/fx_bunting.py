"""fx_bunting: cloth pennant bunting between the lamp posts, rippling in a breeze that pulses with the bass beat.

Run by the walk script's hook (WALK_FX=bunting) with the script's globals. Two parts:
  * BAKE: a clean background Blender (started by this file itself, `blender -b --factory-startup -P fx_bunting.py -- bake`)
    simulates the Cloth modifier + Wind force field for frames F0..F1 and writes ONE point-cache file `cloth_cache/bunting_<hash>.pc2`.
  * LOAD: every render process builds the same mesh and plays that file back with a Mesh Cache modifier (no simulation in the render).
    So all processes show identical geometry for the same frame. The hash covers the SIM section of this file (settings, mesh builder, wind keys, bake code) + PUNCH + the beat grid + the skip list (bunting_skip.json).
  The cache is made lazily on the first load (the hook cannot bake earlier); a lock folder keeps two processes from baking together.
Manual bake:  blender.exe -b --factory-startup -P fx_bunting.py -- bake
"""
import bpy, bmesh, hashlib, json, math, os, random, struct, subprocess, sys, time
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.join(_HERE, 'cloth_cache')

# ==SIM-BEGIN== (everything between the markers is hashed: change it and the cache is baked again)
F0, F1 = -10, 1451                       # baked frame range (the video is 1..1441)
LAMP_POSTS = (-25, -15, -5, 5, 15, 25)   # same as LAMP_X in the walk script
ROW_Y = (-4.4, -13.6)                    # north and south lamp rows
Z_PIN = 4.6                              # cord height at the posts
SAG = 0.40                               # cord drop at mid-span (catenary)
NSEG = 90                                # header segments per 10 m span (0.111 m)
N_FLAGS, FLAG_STEP, FLAG_FIRST = 12, 7, 4   # flags per span, header segments per flag slot, first flag segment
FLAG_W, FLAG_ROWS, FLAG_DZ = 5, 5, 0.11     # flag top width in segments, row count, row height -> 0.56 m wide, 0.55 m tall
HDR = 0.03                               # half height of the cord ribbon
# cloth (a flag is light fabric; the ribbon is stiff so it acts as a cord)
CLOTH = dict(quality=10, mass=0.05, air_damping=1.0, tension_stiffness=5.0, compression_stiffness=3.0, shear_stiffness=3.0,
             bending_stiffness=0.05, tension_damping=3.0, compression_damping=3.0, shear_damping=3.0, bending_damping=0.1,
             tension_stiffness_max=300.0, compression_stiffness_max=300.0, bending_stiffness_max=40.0)
# wind: direction in the xy plane (x along the street, y across it), strength keyframed on the beat grid
WIND_DIR = (0.35, 0.94, 0.0)
W_TROUGH, W_PEAK, W_NOISE = 0.0, 100.0, 0.3   # wind strength between gusts / at a gust peak (at PUNCH 2.5)
GUST = 6.0                              # frames: gust ramp up / down each side of the peak (the cloth smooths it further)
WIND_LEAD = 14.0                        # frames: the wind key peaks this much before the beat, so the flags peak on the beat
if 'BEAT0' not in globals():              # inside the walk script these two already exist (same values); keep them
    BEAT = 12.5
    try:
        BEAT0 = json.load(open(os.path.join(_HERE, 'walk_beats.json')))['beat0'] % BEAT
    except OSError:
        BEAT0 = 8.5
_PUNCH = float(os.environ.get('WALK_PUNCH', '2.5'))
# Flags that would cover a shop wall emblem in view-25..view+25 are left out of the mesh (static removal, the cord stays).
# bunting_skip.json = list of global flag ids (span * N_FLAGS + j), made offline by fx_logs/bunting2/skip_flags.py.
try:
    SKIP = frozenset(json.load(open(os.path.join(_HERE, 'bunting_skip.json'))))
except OSError:
    SKIP = frozenset()


def build_arrays():
    """Mesh data for all spans (same code in the bake process and in the render process, so the vertex order is identical)."""
    V, faces, fmat, pin, hdr = [], [], [], [], []
    tips = []                                      # (apex vertex, flag top-centre vertex) per flag
    cc = 1.6
    sc = lambda u: (math.cosh(cc * (2 * u - 1)) - 1) / (math.cosh(cc) - 1)
    span_i = 0
    for y in ROW_Y:
        for xa, xb in zip(LAMP_POSTS, LAMP_POSTS[1:]):
            top, bot = [], []
            for k in range(NSEG + 1):
                u = k / NSEG
                x = xa + (xb - xa) * u
                zc = Z_PIN - SAG * (1 - sc(u))
                top.append(len(V)); V.append((x, y, zc + HDR))
                bot.append(len(V)); V.append((x, y, zc - HDR))
            hdr += top + bot
            pin += [top[0], bot[0], top[-1], bot[-1]]
            for k in range(NSEG):
                faces.append((top[k], top[k + 1], bot[k + 1], bot[k])); fmat.append(0)
            for j in range(N_FLAGS):
                if span_i * N_FLAGS + j in SKIP:
                    continue
                k0 = FLAG_FIRST + j * FLAG_STEP
                mat = 1 + (j * 3 + span_i * 2) % 7
                dx = (xb - xa) / NSEG
                row = [bot[k0 + i] for i in range(FLAG_W + 1)]
                top_centre = bot[k0 + FLAG_W // 2]
                for r in range(1, FLAG_ROWS + 1):
                    n = FLAG_W + 1 - r
                    new = []
                    zr = V[bot[k0]][2] - r * FLAG_DZ
                    for i in range(n):
                        new.append(len(V)); V.append((V[bot[k0]][0] + (r * 0.5 + i) * dx, y, zr))
                    for i in range(len(row) - 1):
                        faces.append((row[i], row[i + 1], new[i])); fmat.append(mat)
                        if i < len(new) - 1:
                            faces.append((new[i], new[i + 1], row[i + 1])); fmat.append(mat)
                    row = new
                tips.append((row[0], top_centre))
            span_i += 1
    return dict(V=np.array(V, np.float64), faces=faces, fmat=fmat, pin=pin, hdr=hdr, tips=tips)


def make_object(a, name='bunting'):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in a['V']], [], a['faces'])
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def wind_keys():
    """(frame, strength) pairs: one gust every 2 beats (peak at frame BEAT0 + 25 m - lead, a GUST-frame ramp each side), calm in between; gust height varies a little."""
    rr = random.Random(7)
    out = []
    m = int((F0 - 30 - BEAT0) // (2 * BEAT))
    while BEAT0 + m * 2 * BEAT < F1 + 30:
        pk = BEAT0 + m * 2 * BEAT - WIND_LEAD
        out += [(pk - GUST, W_TROUGH), (pk, W_TROUGH + (W_PEAK - W_TROUGH) * (_PUNCH / 2.5) * rr.uniform(0.8, 1.15)), (pk + GUST, W_TROUGH)]
        m += 1
    return out


def bake_main():
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 24
    sc.frame_start, sc.frame_end = F0, F1
    a = build_arrays()
    ob = make_object(a)
    n = len(a['V'])
    vg = ob.vertex_groups
    g_pin, g_stiff, g_bend = vg.new(name='pin'), vg.new(name='stiff'), vg.new(name='bend')
    g_pin.add(a['pin'], 1.0, 'REPLACE')
    g_stiff.add(a['hdr'], 1.0, 'REPLACE')
    g_bend.add(a['hdr'], 1.0, 'REPLACE')
    cm = ob.modifiers.new('Cloth', 'CLOTH')
    st = cm.settings
    for k, v in CLOTH.items():
        setattr(st, k, v)
    st.vertex_group_mass = 'pin'
    st.pin_stiffness = 1.0
    st.vertex_group_structural_stiffness = 'stiff'
    st.vertex_group_bending = 'bend'
    cm.collision_settings.use_collision = False       # simplification: no collision objects (clearance is checked by measurement instead)
    cm.collision_settings.use_self_collision = False
    cm.point_cache.frame_start, cm.point_cache.frame_end = F0, F1
    bpy.ops.object.effector_add(type='WIND', location=(0, 0, 0))
    w = bpy.context.object
    w.name = 'bunting_wind'
    d = np.array(WIND_DIR) / np.linalg.norm(WIND_DIR)
    # a wind field blows along the empty's local +Z: aim +Z at d
    from mathutils import Vector
    w.rotation_euler = Vector((float(d[0]), float(d[1]), float(d[2]))).to_track_quat('Z', 'Y').to_euler()
    w.field.type = 'WIND'
    w.field.noise = W_NOISE
    w.field.seed = 3
    w.field.flow = 0.0
    for f, s in wind_keys():
        w.field.strength = s
        w.field.keyframe_insert('strength', frame=f)
    frames = np.zeros((F1 - F0 + 1, n, 3), np.float32)
    buf = np.zeros(n * 3, np.float32)
    sc.frame_set(F0)
    for i, f in enumerate(range(F0, F1 + 1)):
        sc.frame_set(f)
        e = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        m = e.to_mesh()
        m.vertices.foreach_get('co', buf)
        e.to_mesh_clear()
        frames[i] = buf.reshape(n, 3)
        if i % 200 == 0:
            print('bake frame', f, 'elapsed %.1f s' % (time.time() - t0), flush=True)
    os.makedirs(_CACHE_DIR, exist_ok=True)
    p = cache_path()
    with open(p + '.tmp', 'wb') as fh:
        fh.write(b'POINTCACHE2\0')
        fh.write(struct.pack('<iiffi', 1, n, float(F0), 1.0, F1 - F0 + 1))
        fh.write(frames.tobytes())
    os.replace(p + '.tmp', p)
    print('BAKED %s  %d frames x %d verts  %.1f MB  %.1f s' % (p, F1 - F0 + 1, n, os.path.getsize(p) / 1e6, time.time() - t0), flush=True)


# ==SIM-END==


def cache_key():
    src = open(os.path.join(_HERE, 'fx_bunting.py'), encoding='utf-8').read()
    sim = src.split('# ==SIM-' + 'BEGIN==')[1].split('# ==SIM-' + 'END==')[0]
    return hashlib.sha1((sim + repr((_PUNCH, BEAT0, BEAT, sorted(SKIP)))).encode()).hexdigest()[:10]


def cache_path():
    return os.path.join(_CACHE_DIR, 'bunting_%s.pc2' % cache_key())


def ensure_cache():
    p = cache_path()
    if os.path.exists(p):
        return p
    os.makedirs(_CACHE_DIR, exist_ok=True)
    lock = os.path.join(_CACHE_DIR, '.bake.lock')
    while True:
        try:
            os.mkdir(lock)
            break
        except FileExistsError:
            if time.time() - os.path.getmtime(lock) > 3600:      # stale lock (a bake takes far less than 1 h)
                os.rmdir(lock)
            time.sleep(5)
            if os.path.exists(p):
                return p
    try:
        if not os.path.exists(p):
            print('FX bunting: no cache, baking now (lazy bake, one time)', flush=True)
            r = subprocess.run([bpy.app.binary_path, '-b', '--factory-startup', '-P', os.path.join(_HERE, 'fx_bunting.py'), '--', 'bake'],
                               env=dict(os.environ, WALK_PUNCH=repr(_PUNCH)), capture_output=True, text=True)
            if not os.path.exists(p):
                raise RuntimeError('bunting bake failed:\n' + r.stdout[-2000:] + r.stderr[-2000:])
    finally:
        os.rmdir(lock)
    return p


def load_main():
    a = build_arrays()
    ob = make_object(a)
    ob.data.materials.append(M('#FFF1D8', 0.7))
    for c in PASTELS:
        ob.data.materials.append(M(c, 0.8))
    ob.data.polygons.foreach_set('material_index', a['fmat'])
    ob.data.update()
    mc = ob.modifiers.new('BuntingCache', 'MESH_CACHE')
    mc.cache_format = 'PC2'
    mc.filepath = ensure_cache()
    mc.forward_axis, mc.up_axis = 'POS_Y', 'POS_Z'
    mc.time_mode, mc.play_mode, mc.interpolation = 'FRAME', 'SCENE', 'NONE'
    mc.frame_start = F0                      # sample i of the file = frame F0 + i
    print('FX bunting: %d verts, cache %s' % (len(a['V']), mc.filepath))


if 'SHOP_LIST' in globals():                 # run by the walk script's hook
    load_main()
elif '--' in sys.argv and sys.argv[sys.argv.index('--') + 1:][:1] == ['bake']:
    bake_main()
