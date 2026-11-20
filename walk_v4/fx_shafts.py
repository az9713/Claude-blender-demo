# fx_shafts.py: soft sun shafts. Runs inside build_neighborhood_walk_v2.py (globals: scene, world, sun, ...).
# A thin, low scattering volume in a box object (ground to 6 m, density fades with height), lit by morning_sun. Building shadows carve faint shafts in it.
# v4 (density 0.001, sun volume factor 6, top 6 m) replaces v3 (0.003, 4.5, top 28 m), which washed out saturation: see fx_logs/shafts2/log.md.
# Settings come from env WALK_SH_* only for tuning; defaults are the final values.
_E = lambda k, d: float(os.environ.get('WALK_SH_' + k, d))   # tuning only; defaults below are the final values
SH_DENS = _E('DENS', 0.001)      # scatter density per metre
SH_ANI = _E('ANI', 0.8)         # forward scattering (sun side glows)
SH_END = _E('END', 60)           # haze range in metres (volume ends here)
SH_SAMP = int(_E('SAMP', 48))    # volumetric samples (depth slices)
SH_TILE = os.environ.get('WALK_SH_TILE', '4')
SH_TOP = _E('TOP', 6.0)          # haze box top in metres: below the roofs (7.4-8.2 m), so the sky is not veiled (v3 had 28 m and lost 50% of the sky saturation)
SH_FADE = _E('FADE', 1.5)        # density is full below this height and fades to 0 at the box top
SH_VF = _E('VF', 6.0)            # sun volume factor: scatter strength without more extinction (more in-scatter per unit of extinction; the product DENS*VF sets colour and contrast loss)

# A world volume darkened the whole frame even at density 0.0001 (measured), so the haze is a box object with a volume material.
_mat = bpy.data.materials.new('shaft_haze')
_mat.use_nodes = True
_nt = _mat.node_tree
for _n_ in list(_nt.nodes):
    _nt.nodes.remove(_n_)
_out = _nt.nodes.new('ShaderNodeOutputMaterial')
_vs = _nt.nodes.new('ShaderNodeVolumeScatter')
_vs.inputs['Color'].default_value = (*srgb('#FFE9CC'), 1)   # warm cream, keeps the pastel palette
# density = SH_DENS * height fade: 1 below SH_FADE, 0 at SH_TOP (Geometry position z -> Map Range)
_gp = _nt.nodes.new('ShaderNodeNewGeometry')
_sx = _nt.nodes.new('ShaderNodeSeparateXYZ')
_mr = _nt.nodes.new('ShaderNodeMapRange')
_mr.inputs['From Min'].default_value = SH_TOP
_mr.inputs['From Max'].default_value = SH_FADE
_mr.inputs['To Min'].default_value = 0.0
_mr.inputs['To Max'].default_value = SH_DENS
_mr.clamp = True
_nt.links.new(_gp.outputs['Position'], _sx.inputs['Vector'])
_nt.links.new(_sx.outputs['Z'], _mr.inputs['Value'])
_mr.name = 'hmap'
_nt.links.new(_mr.outputs['Result'], _vs.inputs['Density'])
_vs.inputs['Anisotropy'].default_value = SH_ANI
_nt.links.new(_vs.outputs['Volume'], _out.inputs['Volume'])
_bm = bmesh.new()
bmesh.ops.create_cube(_bm, size=1.0)
_me = bpy.data.meshes.new('shaft_haze')
_bm.to_mesh(_me)
_bm.free()
_hz = bpy.data.objects.new('shaft_haze', _me)
scene.collection.objects.link(_hz)
_hz.location = (-5, -9, SH_TOP / 2)  # covers the street, both rows, from the ground up to SH_TOP
_hz.scale = (120, 40, SH_TOP)
_hz.data.materials.append(_mat)
_hz.visible_shadow = False
_hz.display_type = 'WIRE'

_ee = scene.eevee
_ee.use_volumetric_shadows = True
_ee.volumetric_samples = int(SH_SAMP)
_ee.volumetric_tile_size = SH_TILE
_ee.volumetric_shadow_samples = 16
_ee.use_volume_custom_range = True
_ee.volumetric_start = 0.1
_ee.volumetric_end = SH_END
sun.data.volume_factor = SH_VF
