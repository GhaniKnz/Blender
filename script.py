"""
Cinematic Space Trailer Generator (Blender / bpy)
=================================================
Copiez/collez ce script dans Blender (Scripting) puis Run Script.
Le script construit automatiquement une scène spatiale cinématique (~60s)
avec Terre, Lune, Soleil, météorite, impact, explosion, étoiles, caméras multi-plans.

IMPORTANT:
- Les chemins de textures/HDRI sont des placeholders: remplacez-les dans ASSET_PATHS.
- Le script reste 100% procédural en fallback si les textures ne sont pas disponibles.
"""

import bpy
import math
import random
from mathutils import Vector, Euler

# ============================================================
# CONFIG GLOBALE (PERSONNALISATION RAPIDE)
# ============================================================
CONFIG = {
    "fps": 24,
    "duration_seconds": 60,              # >= 60s
    "resolution_x": 1920,
    "resolution_y": 1080,
    "render_samples": 256,
    "preview_samples": 64,
    "earth_radius": 2.0,
    "moon_radius": 0.55,
    "moon_orbit_radius": 7.5,
    "earth_rotation_turns": 2.0,
    "moon_orbit_turns": 1.3,
    "moon_spin_turns": 1.0,
    "meteor_start": Vector((28.0, -14.0, 7.0)),
    "meteor_end": Vector((1.95, -0.4, 0.25)),   # zone d'impact sur Terre
    "meteor_start_frame": 780,
    "impact_frame": 1140,
    "explosion_strength": 160.0,
}

# ------------------------------------------------------------
# CHEMINS ASSETS (A MODIFIER)
# ------------------------------------------------------------
ASSET_PATHS = {
    # Terre
    "earth_albedo": "//assets/textures/earth/earth_albedo_8k.jpg",
    "earth_normal": "//assets/textures/earth/earth_normal_8k.jpg",
    "earth_roughness": "//assets/textures/earth/earth_roughness_8k.jpg",
    "earth_clouds": "//assets/textures/earth/earth_clouds_8k.png",
    "earth_night": "//assets/textures/earth/earth_night_8k.jpg",

    # Lune
    "moon_albedo": "//assets/textures/moon/moon_albedo_4k.jpg",
    "moon_normal": "//assets/textures/moon/moon_normal_4k.jpg",
    "moon_roughness": "//assets/textures/moon/moon_roughness_4k.jpg",

    # Soleil / espace
    "space_hdri": "//assets/hdri/space_hdr_16k.exr",

    # FX optionnels
    "meteor_albedo": "//assets/textures/meteor/meteor_albedo_4k.jpg",
    "meteor_normal": "//assets/textures/meteor/meteor_normal_4k.jpg",
}


# ============================================================
# OUTILS
# ============================================================
def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    for block_list in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.textures,
        bpy.data.images,
        bpy.data.curves,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.collections,
        bpy.data.worlds,
    ):
        for block in list(block_list):
            if block.users == 0:
                block_list.remove(block)


def ensure_collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        if parent:
            parent.children.link(col)
        else:
            bpy.context.scene.collection.children.link(col)
    return col


def link_to_collection(obj, col):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)


def safe_load_image(path):
    try:
        img = bpy.data.images.load(path, check_existing=True)
        return img
    except Exception:
        print(f"[INFO] Texture introuvable, fallback procédural: {path}")
        return None


def add_subsurf(obj, levels=3, render_levels=4):
    mod = obj.modifiers.new(name="Subsurf", type='SUBSURF')
    mod.levels = levels
    mod.render_levels = render_levels


def make_sphere(name, radius, location=(0, 0, 0), segments=128, rings=64):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=radius,
        segments=segments,
        ring_count=rings,
        location=location,
    )
    obj = bpy.context.active_object
    obj.name = name
    return obj


# ============================================================
# RENDER / SCENE
# ============================================================
def setup_render(scene):
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = CONFIG["render_samples"]
    scene.cycles.preview_samples = CONFIG["preview_samples"]
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.max_bounces = 10
    scene.cycles.diffuse_bounces = 4
    scene.cycles.glossy_bounces = 4
    scene.cycles.transmission_bounces = 8
    scene.cycles.volume_bounces = 2

    scene.render.fps = CONFIG["fps"]
    scene.frame_start = 1
    scene.frame_end = CONFIG["fps"] * CONFIG["duration_seconds"]

    scene.render.resolution_x = CONFIG["resolution_x"]
    scene.render.resolution_y = CONFIG["resolution_y"]
    scene.render.resolution_percentage = 100

    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.45

    scene.view_settings.view_transform = 'Filmic'
    scene.view_settings.look = 'High Contrast'
    scene.view_settings.exposure = 0.1
    scene.view_settings.gamma = 0.95

    scene.use_nodes = True
    tree = scene.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    rl = nodes.new(type='CompositorNodeRLayers')
    glare = nodes.new(type='CompositorNodeGlare')
    glare.glare_type = 'FOG_GLOW'
    glare.quality = 'HIGH'
    glare.threshold = 0.75
    glare.size = 7

    lens = nodes.new(type='CompositorNodeLensdist')
    lens.inputs['Dispersion'].default_value = 0.02

    color_balance = nodes.new(type='CompositorNodeColorBalance')
    color_balance.correction_method = 'LIFT_GAMMA_GAIN'
    color_balance.lift = (1.0, 1.0, 1.02)
    color_balance.gamma = (1.0, 1.0, 1.0)
    color_balance.gain = (1.08, 1.04, 1.0)

    vignette = nodes.new(type='CompositorNodeEllipseMask')
    vignette.width = 0.86
    vignette.height = 0.76
    blur = nodes.new(type='CompositorNodeBlur')
    blur.filter_type = 'GAUSS'
    blur.size_x = 350
    blur.size_y = 350
    invert = nodes.new(type='CompositorNodeInvert')
    mix = nodes.new(type='CompositorNodeMixRGB')
    mix.blend_type = 'MULTIPLY'
    mix.inputs[0].default_value = 0.25

    comp = nodes.new(type='CompositorNodeComposite')

    links.new(rl.outputs['Image'], glare.inputs['Image'])
    links.new(glare.outputs['Image'], lens.inputs['Image'])
    links.new(lens.outputs['Image'], color_balance.inputs['Image'])

    links.new(vignette.outputs['Mask'], blur.inputs['Image'])
    links.new(blur.outputs['Image'], invert.inputs['Color'])

    links.new(color_balance.outputs['Image'], mix.inputs[1])
    links.new(invert.outputs['Color'], mix.inputs[2])
    links.new(mix.outputs['Image'], comp.inputs['Image'])


def setup_world(scene):
    world = bpy.data.worlds.new("CinematicWorld")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nodes = nt.nodes
    links = nt.links
    nodes.clear()

    bg = nodes.new(type='ShaderNodeBackground')
    bg.inputs['Strength'].default_value = 1.0

    out = nodes.new(type='ShaderNodeOutputWorld')

    hdri_img = safe_load_image(ASSET_PATHS["space_hdri"])
    if hdri_img:
        tex = nodes.new(type='ShaderNodeTexEnvironment')
        tex.image = hdri_img
        mapping = nodes.new(type='ShaderNodeMapping')
        texcoord = nodes.new(type='ShaderNodeTexCoord')
        links.new(texcoord.outputs['Generated'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
        links.new(tex.outputs['Color'], bg.inputs['Color'])
        bg.inputs['Strength'].default_value = 0.65
    else:
        bg.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)

    links.new(bg.outputs['Background'], out.inputs['Surface'])


# ============================================================
# MATERIAUX
# ============================================================
def create_earth_material(name="MAT_Earth"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Specular IOR Level'].default_value = 0.25
    bsdf.inputs['Roughness'].default_value = 0.5

    output = nodes.new('ShaderNodeOutputMaterial')

    tex_coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    links.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])

    albedo = safe_load_image(ASSET_PATHS["earth_albedo"])
    normal = safe_load_image(ASSET_PATHS["earth_normal"])
    rough = safe_load_image(ASSET_PATHS["earth_roughness"])
    night = safe_load_image(ASSET_PATHS["earth_night"])

    if albedo:
        albedo_tex = nodes.new('ShaderNodeTexImage')
        albedo_tex.image = albedo
        links.new(mapping.outputs['Vector'], albedo_tex.inputs['Vector'])
        links.new(albedo_tex.outputs['Color'], bsdf.inputs['Base Color'])
    else:
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 8.0
        ramp = nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].color = (0.04, 0.12, 0.30, 1)
        ramp.color_ramp.elements[1].color = (0.10, 0.35, 0.12, 1)
        links.new(mapping.outputs['Vector'], noise.inputs['Vector'])
        links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
        links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])

    if rough:
        rough_tex = nodes.new('ShaderNodeTexImage')
        rough_tex.image = rough
        rough_tex.image.colorspace_settings.name = 'Non-Color'
        links.new(mapping.outputs['Vector'], rough_tex.inputs['Vector'])
        links.new(rough_tex.outputs['Color'], bsdf.inputs['Roughness'])

    if normal:
        n_tex = nodes.new('ShaderNodeTexImage')
        n_tex.image = normal
        n_tex.image.colorspace_settings.name = 'Non-Color'
        nmap = nodes.new('ShaderNodeNormalMap')
        nmap.inputs['Strength'].default_value = 1.0
        links.new(mapping.outputs['Vector'], n_tex.inputs['Vector'])
        links.new(n_tex.outputs['Color'], nmap.inputs['Color'])
        links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])

    if night:
        night_tex = nodes.new('ShaderNodeTexImage')
        night_tex.image = night
        mix = nodes.new('ShaderNodeMixRGB')
        mix.blend_type = 'ADD'
        mix.inputs[0].default_value = 0.35
        fres = nodes.new('ShaderNodeFresnel')
        fres.inputs['IOR'].default_value = 1.08
        inv = nodes.new('ShaderNodeInvert')
        links.new(mapping.outputs['Vector'], night_tex.inputs['Vector'])
        links.new(fres.outputs['Fac'], inv.inputs['Color'])
        links.new(inv.outputs['Color'], mix.inputs[0])
        links.new(night_tex.outputs['Color'], mix.inputs[2])
        links.new(mix.outputs['Color'], bsdf.inputs['Emission Color'])
        bsdf.inputs['Emission Strength'].default_value = 0.25

    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    return mat


def create_cloud_material(name="MAT_Clouds"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = 'BLEND'
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    principled = nodes.new('ShaderNodeBsdfPrincipled')
    principled.inputs['Base Color'].default_value = (0.93, 0.96, 1.0, 1)
    principled.inputs['Roughness'].default_value = 0.5
    principled.inputs['Alpha'].default_value = 0.25

    output = nodes.new('ShaderNodeOutputMaterial')
    tex_coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    links.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])

    clouds = safe_load_image(ASSET_PATHS["earth_clouds"])
    if clouds:
        ctex = nodes.new('ShaderNodeTexImage')
        ctex.image = clouds
        links.new(mapping.outputs['Vector'], ctex.inputs['Vector'])
        links.new(ctex.outputs['Color'], principled.inputs['Base Color'])
        links.new(ctex.outputs['Alpha'], principled.inputs['Alpha'])
    else:
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 10.0
        ramp = nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position = 0.48
        ramp.color_ramp.elements[1].position = 0.62
        links.new(mapping.outputs['Vector'], noise.inputs['Vector'])
        links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
        links.new(ramp.outputs['Color'], principled.inputs['Alpha'])

    links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    return mat


def create_atmosphere_material(name="MAT_Atmosphere"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = 'ADD'
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    transparent = nodes.new('ShaderNodeBsdfTransparent')
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (0.16, 0.45, 1.0, 1)
    emission.inputs['Strength'].default_value = 0.9

    fresnel = nodes.new('ShaderNodeLayerWeight')
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.42
    ramp.color_ramp.elements[1].position = 0.95

    mix = nodes.new('ShaderNodeMixShader')
    out = nodes.new('ShaderNodeOutputMaterial')

    links.new(fresnel.outputs['Facing'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], mix.inputs['Fac'])
    links.new(transparent.outputs['BSDF'], mix.inputs[1])
    links.new(emission.outputs['Emission'], mix.inputs[2])
    links.new(mix.outputs['Shader'], out.inputs['Surface'])
    return mat


def create_moon_material(name="MAT_Moon"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.85
    bsdf.inputs['Specular IOR Level'].default_value = 0.12

    out = nodes.new('ShaderNodeOutputMaterial')
    tc = nodes.new('ShaderNodeTexCoord')
    mp = nodes.new('ShaderNodeMapping')
    links.new(tc.outputs['Generated'], mp.inputs['Vector'])

    albedo = safe_load_image(ASSET_PATHS["moon_albedo"])
    normal = safe_load_image(ASSET_PATHS["moon_normal"])
    rough = safe_load_image(ASSET_PATHS["moon_roughness"])

    if albedo:
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = albedo
        links.new(mp.outputs['Vector'], tex.inputs['Vector'])
        links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    else:
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 24.0
        ramp = nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].color = (0.25, 0.25, 0.25, 1)
        ramp.color_ramp.elements[1].color = (0.55, 0.55, 0.55, 1)
        links.new(mp.outputs['Vector'], noise.inputs['Vector'])
        links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
        links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])

    if rough:
        rtex = nodes.new('ShaderNodeTexImage')
        rtex.image = rough
        rtex.image.colorspace_settings.name = 'Non-Color'
        links.new(mp.outputs['Vector'], rtex.inputs['Vector'])
        links.new(rtex.outputs['Color'], bsdf.inputs['Roughness'])

    if normal:
        ntex = nodes.new('ShaderNodeTexImage')
        ntex.image = normal
        ntex.image.colorspace_settings.name = 'Non-Color'
        nmap = nodes.new('ShaderNodeNormalMap')
        nmap.inputs['Strength'].default_value = 0.65
        links.new(mp.outputs['Vector'], ntex.inputs['Vector'])
        links.new(ntex.outputs['Color'], nmap.inputs['Color'])
        links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])

    links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def create_sun_material(name="MAT_Sun"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (1.0, 0.75, 0.45, 1)
    emission.inputs['Strength'].default_value = 35.0

    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 4.0
    noise.inputs['Detail'].default_value = 12.0
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (0.95, 0.20, 0.03, 1)
    ramp.color_ramp.elements[1].color = (1.0, 0.9, 0.45, 1)

    out = nodes.new('ShaderNodeOutputMaterial')
    links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], emission.inputs['Color'])
    links.new(emission.outputs['Emission'], out.inputs['Surface'])
    return mat


def create_starfield_material(name="MAT_Starfield"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 1.9
    bg = nodes.new('ShaderNodeBackground')

    tc = nodes.new('ShaderNodeTexCoord')
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 1200.0
    noise.inputs['Detail'].default_value = 2.0
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.988
    ramp.color_ramp.elements[1].position = 0.995

    nebula_noise = nodes.new('ShaderNodeTexNoise')
    nebula_noise.inputs['Scale'].default_value = 2.2
    nebula_noise.inputs['Detail'].default_value = 14
    nebula_ramp = nodes.new('ShaderNodeValToRGB')
    nebula_ramp.color_ramp.elements[0].position = 0.35
    nebula_ramp.color_ramp.elements[1].position = 0.78
    nebula_ramp.color_ramp.elements[0].color = (0.02, 0.02, 0.05, 1)
    nebula_ramp.color_ramp.elements[1].color = (0.11, 0.05, 0.17, 1)

    mix_rgb = nodes.new('ShaderNodeMixRGB')
    mix_rgb.blend_type = 'ADD'
    mix_rgb.inputs['Fac'].default_value = 1.0

    out = nodes.new('ShaderNodeOutputMaterial')

    links.new(tc.outputs['Generated'], noise.inputs['Vector'])
    links.new(tc.outputs['Generated'], nebula_noise.inputs['Vector'])
    links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
    links.new(nebula_noise.outputs['Fac'], nebula_ramp.inputs['Fac'])

    links.new(ramp.outputs['Color'], mix_rgb.inputs[1])
    links.new(nebula_ramp.outputs['Color'], mix_rgb.inputs[2])
    links.new(mix_rgb.outputs['Color'], emission.inputs['Color'])
    links.new(emission.outputs['Emission'], out.inputs['Surface'])
    return mat


def create_meteor_material(name="MAT_Meteor"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.82
    bsdf.inputs['Metallic'].default_value = 0.05

    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (1.0, 0.27, 0.05, 1)
    emission.inputs['Strength'].default_value = 3.0

    fres = nodes.new('ShaderNodeLayerWeight')
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.7
    ramp.color_ramp.elements[1].position = 1.0

    add = nodes.new('ShaderNodeAddShader')
    out = nodes.new('ShaderNodeOutputMaterial')

    albedo = safe_load_image(ASSET_PATHS["meteor_albedo"])
    normal = safe_load_image(ASSET_PATHS["meteor_normal"])

    tc = nodes.new('ShaderNodeTexCoord')
    mp = nodes.new('ShaderNodeMapping')
    links.new(tc.outputs['Object'], mp.inputs['Vector'])

    if albedo:
        tex = nodes.new('ShaderNodeTexImage')
        tex.image = albedo
        links.new(mp.outputs['Vector'], tex.inputs['Vector'])
        links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    else:
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 14.0
        ramp_col = nodes.new('ShaderNodeValToRGB')
        ramp_col.color_ramp.elements[0].color = (0.08, 0.07, 0.06, 1)
        ramp_col.color_ramp.elements[1].color = (0.25, 0.21, 0.17, 1)
        links.new(mp.outputs['Vector'], noise.inputs['Vector'])
        links.new(noise.outputs['Fac'], ramp_col.inputs['Fac'])
        links.new(ramp_col.outputs['Color'], bsdf.inputs['Base Color'])

    if normal:
        ntex = nodes.new('ShaderNodeTexImage')
        ntex.image = normal
        ntex.image.colorspace_settings.name = 'Non-Color'
        nmap = nodes.new('ShaderNodeNormalMap')
        nmap.inputs['Strength'].default_value = 1.2
        links.new(mp.outputs['Vector'], ntex.inputs['Vector'])
        links.new(ntex.outputs['Color'], nmap.inputs['Color'])
        links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])

    links.new(fres.outputs['Facing'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], emission.inputs['Strength'])
    links.new(bsdf.outputs['BSDF'], add.inputs[0])
    links.new(emission.outputs['Emission'], add.inputs[1])
    links.new(add.outputs['Shader'], out.inputs['Surface'])
    return mat


# ============================================================
# CREATION OBJETS
# ============================================================
def create_earth_system(col_planets):
    earth = make_sphere("Earth", CONFIG["earth_radius"], (0, 0, 0), 192, 96)
    add_subsurf(earth, 2, 3)
    earth.data.materials.append(create_earth_material())
    link_to_collection(earth, col_planets)

    clouds = make_sphere("Earth_Clouds", CONFIG["earth_radius"] * 1.008, (0, 0, 0), 192, 96)
    clouds.data.materials.append(create_cloud_material())
    link_to_collection(clouds, col_planets)

    atmosphere = make_sphere("Earth_Atmosphere", CONFIG["earth_radius"] * 1.03, (0, 0, 0), 192, 96)
    atmosphere.data.materials.append(create_atmosphere_material())
    link_to_collection(atmosphere, col_planets)

    # Rotation Terre + nuages
    f_end = bpy.context.scene.frame_end
    earth.rotation_euler = Euler((0, 0, 0), 'XYZ')
    earth.keyframe_insert(data_path="rotation_euler", frame=1)
    earth.rotation_euler = Euler((0, 0, math.radians(360 * CONFIG["earth_rotation_turns"])), 'XYZ')
    earth.keyframe_insert(data_path="rotation_euler", frame=f_end)

    clouds.rotation_euler = Euler((0, 0, 0), 'XYZ')
    clouds.keyframe_insert(data_path="rotation_euler", frame=1)
    clouds.rotation_euler = Euler((0, 0, math.radians(360 * (CONFIG["earth_rotation_turns"] * 1.15))), 'XYZ')
    clouds.keyframe_insert(data_path="rotation_euler", frame=f_end)

    for obj in [earth, clouds]:
        for fc in obj.animation_data.action.fcurves:
            fc.modifiers.new(type='CYCLES')
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'

    return earth, clouds, atmosphere


def create_moon(col_planets, earth_obj):
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
    moon_orbit = bpy.context.active_object
    moon_orbit.name = "Moon_Orbit_Rig"
    link_to_collection(moon_orbit, col_planets)

    moon = make_sphere("Moon", CONFIG["moon_radius"], (CONFIG["moon_orbit_radius"], 0, 0), 128, 64)
    moon.data.materials.append(create_moon_material())
    link_to_collection(moon, col_planets)
    moon.parent = moon_orbit

    f_end = bpy.context.scene.frame_end
    moon_orbit.rotation_euler = (math.radians(12), 0, 0)
    moon_orbit.keyframe_insert(data_path='rotation_euler', frame=1)
    moon_orbit.rotation_euler = (math.radians(12), 0, math.radians(360 * CONFIG["moon_orbit_turns"]))
    moon_orbit.keyframe_insert(data_path='rotation_euler', frame=f_end)

    moon.rotation_euler = (0, 0, 0)
    moon.keyframe_insert(data_path='rotation_euler', frame=1)
    moon.rotation_euler = (0, 0, math.radians(360 * CONFIG["moon_spin_turns"]))
    moon.keyframe_insert(data_path='rotation_euler', frame=f_end)

    for obj in [moon_orbit, moon]:
        for fc in obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'

    return moon, moon_orbit


def create_sun(col_lights):
    sun_light_data = bpy.data.lights.new(name="Sun_Light", type='SUN')
    sun_light_data.energy = 10.0
    sun_light_data.angle = math.radians(0.28)
    sun_light = bpy.data.objects.new("Sun_Light", sun_light_data)
    sun_light.location = (-35, -18, 12)
    bpy.context.scene.collection.objects.link(sun_light)
    link_to_collection(sun_light, col_lights)

    # Animation légère: "lever de soleil" spatial
    sun_light.rotation_euler = Euler((math.radians(58), math.radians(0), math.radians(25)), 'XYZ')
    sun_light.keyframe_insert(data_path='rotation_euler', frame=1)
    sun_light.rotation_euler = Euler((math.radians(52), math.radians(2), math.radians(37)), 'XYZ')
    sun_light.keyframe_insert(data_path='rotation_euler', frame=360)

    sun_mesh = make_sphere("Sun_Visual", 4.0, (-42, -24, 18), 96, 48)
    sun_mesh.data.materials.append(create_sun_material())
    link_to_collection(sun_mesh, col_lights)

    return sun_light, sun_mesh


def create_space_background(col_space):
    # Dôme d'étoiles procédural (faces inversées)
    star_dome = make_sphere("StarDome", 220, (0, 0, 0), 128, 64)
    star_dome.scale = (-1, 1, 1)
    star_dome.data.materials.append(create_starfield_material())
    link_to_collection(star_dome, col_space)

    # Planètes lointaines décoratives
    for i in range(3):
        r = random.uniform(0.8, 2.4)
        loc = (
            random.uniform(-120, 140),
            random.uniform(-100, 130),
            random.uniform(-70, 90),
        )
        p = make_sphere(f"DistantPlanet_{i+1}", r, loc, 64, 32)
        mat = bpy.data.materials.new(f"MAT_DistantPlanet_{i+1}")
        mat.use_nodes = True
        n = mat.node_tree.nodes
        l = mat.node_tree.links
        n.clear()
        bsdf = n.new('ShaderNodeBsdfPrincipled')
        noise = n.new('ShaderNodeTexNoise')
        ramp = n.new('ShaderNodeValToRGB')
        out = n.new('ShaderNodeOutputMaterial')
        noise.inputs['Scale'].default_value = random.uniform(4, 14)
        ramp.color_ramp.elements[0].color = (random.uniform(0.02, 0.2), random.uniform(0.05, 0.3), random.uniform(0.2, 0.5), 1)
        ramp.color_ramp.elements[1].color = (random.uniform(0.2, 0.8), random.uniform(0.1, 0.6), random.uniform(0.05, 0.3), 1)
        l.new(noise.outputs['Fac'], ramp.inputs['Fac'])
        l.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
        l.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
        p.data.materials.append(mat)
        link_to_collection(p, col_space)


def create_meteor_and_fx(col_vfx, earth_obj):
    meteor = bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=0.45, location=CONFIG["meteor_start"])
    meteor = bpy.context.active_object
    meteor.name = "Meteor"
    add_subsurf(meteor, 1, 2)
    meteor.data.materials.append(create_meteor_material())
    link_to_collection(meteor, col_vfx)

    disp = meteor.modifiers.new("Meteor_Displace", 'DISPLACE')
    tex = bpy.data.textures.new("MeteorNoise", 'CLOUDS')
    tex.noise_scale = 0.28
    disp.texture = tex
    disp.strength = 0.22

    # Traînée lumineuse via courbe
    curve_data = bpy.data.curves.new('MeteorTrailCurve', type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.bevel_depth = 0.08
    curve_data.bevel_resolution = 8
    spline = curve_data.splines.new('POLY')
    spline.points.add(2)
    spline.points[0].co = (*CONFIG["meteor_start"], 1)
    mid = CONFIG["meteor_start"].lerp(CONFIG["meteor_end"], 0.35) + Vector((0, 0, 2.2))
    spline.points[1].co = (*mid, 1)
    spline.points[2].co = (*CONFIG["meteor_end"], 1)
    trail_obj = bpy.data.objects.new("MeteorTrail", curve_data)
    bpy.context.scene.collection.objects.link(trail_obj)
    link_to_collection(trail_obj, col_vfx)

    trail_mat = bpy.data.materials.new("MAT_MeteorTrail")
    trail_mat.use_nodes = True
    n = trail_mat.node_tree.nodes
    l = trail_mat.node_tree.links
    n.clear()
    em = n.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (1.0, 0.35, 0.05, 1)
    em.inputs['Strength'].default_value = 25
    tr = n.new('ShaderNodeBsdfTransparent')
    mix = n.new('ShaderNodeMixShader')
    lw = n.new('ShaderNodeLayerWeight')
    out = n.new('ShaderNodeOutputMaterial')
    l.new(lw.outputs['Facing'], mix.inputs['Fac'])
    l.new(tr.outputs['BSDF'], mix.inputs[1])
    l.new(em.outputs['Emission'], mix.inputs[2])
    l.new(mix.outputs['Shader'], out.inputs['Surface'])
    trail_mat.blend_method = 'ADD'
    trail_obj.data.materials.append(trail_mat)

    # Contrainte: la traînée suit la météorite
    constr = trail_obj.constraints.new('FOLLOW_PATH')
    constr.target = trail_obj
    trail_obj.hide_render = False

    # Animation trajectoire météorite
    meteor.location = CONFIG["meteor_start"]
    meteor.keyframe_insert(data_path='location', frame=CONFIG["meteor_start_frame"])
    meteor.location = CONFIG["meteor_end"]
    meteor.keyframe_insert(data_path='location', frame=CONFIG["impact_frame"])

    meteor.rotation_euler = Euler((0, 0, 0), 'XYZ')
    meteor.keyframe_insert(data_path='rotation_euler', frame=CONFIG["meteor_start_frame"])
    meteor.rotation_euler = Euler((math.radians(810), math.radians(190), math.radians(250)), 'XYZ')
    meteor.keyframe_insert(data_path='rotation_euler', frame=CONFIG["impact_frame"])

    # Lumière de rentrée atmosphérique
    impact_light_data = bpy.data.lights.new("ImpactFlashLight", type='POINT')
    impact_light_data.energy = 0.0
    impact_light_data.color = (1.0, 0.48, 0.2)
    impact_light_data.shadow_soft_size = 0.9
    impact_light = bpy.data.objects.new("ImpactFlashLight", impact_light_data)
    impact_light.location = CONFIG["meteor_end"]
    bpy.context.scene.collection.objects.link(impact_light)
    link_to_collection(impact_light, col_vfx)

    impact_light_data.keyframe_insert(data_path='energy', frame=CONFIG["impact_frame"] - 2)
    impact_light_data.energy = 120000.0
    impact_light_data.keyframe_insert(data_path='energy', frame=CONFIG["impact_frame"] + 2)
    impact_light_data.energy = 8000.0
    impact_light_data.keyframe_insert(data_path='energy', frame=CONFIG["impact_frame"] + 16)
    impact_light_data.energy = 0.0
    impact_light_data.keyframe_insert(data_path='energy', frame=CONFIG["impact_frame"] + 38)

    # Sphère d'explosion
    explosion = make_sphere("ExplosionSphere", 0.15, CONFIG["meteor_end"], 96, 48)
    link_to_collection(explosion, col_vfx)
    ex_mat = bpy.data.materials.new("MAT_Explosion")
    ex_mat.use_nodes = True
    n = ex_mat.node_tree.nodes
    l = ex_mat.node_tree.links
    n.clear()
    em = n.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (1.0, 0.55, 0.18, 1)
    em.inputs['Strength'].default_value = CONFIG["explosion_strength"]
    noise = n.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 14.0
    ramp = n.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[1].position = 0.92
    out = n.new('ShaderNodeOutputMaterial')
    l.new(noise.outputs['Fac'], ramp.inputs['Fac'])
    l.new(ramp.outputs['Color'], em.inputs['Color'])
    l.new(em.outputs['Emission'], out.inputs['Surface'])
    explosion.data.materials.append(ex_mat)

    explosion.hide_viewport = True
    explosion.hide_render = True
    explosion.keyframe_insert(data_path='hide_viewport', frame=CONFIG["impact_frame"] - 1)
    explosion.keyframe_insert(data_path='hide_render', frame=CONFIG["impact_frame"] - 1)
    explosion.hide_viewport = False
    explosion.hide_render = False
    explosion.keyframe_insert(data_path='hide_viewport', frame=CONFIG["impact_frame"])
    explosion.keyframe_insert(data_path='hide_render', frame=CONFIG["impact_frame"])

    explosion.scale = (0.01, 0.01, 0.01)
    explosion.keyframe_insert(data_path='scale', frame=CONFIG["impact_frame"])
    explosion.scale = (4.8, 4.8, 4.8)
    explosion.keyframe_insert(data_path='scale', frame=CONFIG["impact_frame"] + 16)
    explosion.scale = (7.2, 7.2, 7.2)
    explosion.keyframe_insert(data_path='scale', frame=CONFIG["impact_frame"] + 48)

    return meteor, trail_obj, explosion


# ============================================================
# CAMERAS CINEMATIQUES
# ============================================================
def create_camera(name, location, rotation_deg, lens=50):
    cam_data = bpy.data.cameras.new(name + "_Data")
    cam_data.lens = lens
    cam_data.dof.use_dof = True
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = location
    cam.rotation_euler = Euler(tuple(math.radians(a) for a in rotation_deg), 'XYZ')
    return cam


def add_camera_marker(scene, frame, cam, marker_name):
    m = scene.timeline_markers.new(marker_name, frame=frame)
    m.camera = cam


def setup_cameras(scene, earth, moon, meteor):
    # Cibles DOF
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=earth.location)
    focus_earth = bpy.context.active_object
    focus_earth.name = "Focus_Earth"

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=moon.matrix_world.translation)
    focus_moon = bpy.context.active_object
    focus_moon.name = "Focus_Moon"

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=meteor.location)
    focus_meteor = bpy.context.active_object
    focus_meteor.name = "Focus_Meteor"

    cams = {}
    cams["wide"] = create_camera("CAM_WideSpace", (18, -20, 10), (65, 0, 42), lens=28)
    cams["earth_close"] = create_camera("CAM_EarthClose", (6.2, -4.4, 2.2), (82, 0, 48), lens=75)
    cams["moon_orbit"] = create_camera("CAM_MoonOrbit", (10.0, 3.0, 2.0), (76, 0, 112), lens=60)
    cams["sunrise"] = create_camera("CAM_Sunrise", (5.0, -7.0, 0.6), (90, 0, 18), lens=65)
    cams["travel"] = create_camera("CAM_Travel", (0.0, -10.5, 4.2), (75, 0, 0), lens=40)
    cams["meteor_drama"] = create_camera("CAM_MeteorDrama", (22.5, -11.2, 8.0), (66, -2, 61), lens=85)
    cams["meteor_follow"] = create_camera("CAM_MeteorFollow", (25.0, -13.0, 7.5), (67, 0, 60), lens=55)
    cams["impact"] = create_camera("CAM_Impact", (3.2, -2.2, 1.2), (87, 0, 42), lens=90)
    cams["final"] = create_camera("CAM_FinalEpic", (15.0, -14.0, 7.0), (67, 0, 43), lens=38)

    for cam in cams.values():
        cam.data.dof.aperture_fstop = 1.8

    cams["wide"].data.dof.focus_object = focus_earth
    cams["earth_close"].data.dof.focus_object = focus_earth
    cams["moon_orbit"].data.dof.focus_object = focus_moon
    cams["sunrise"].data.dof.focus_object = focus_earth
    cams["travel"].data.dof.focus_object = focus_earth
    cams["meteor_drama"].data.dof.focus_object = focus_meteor
    cams["meteor_follow"].data.dof.focus_object = focus_meteor
    cams["impact"].data.dof.focus_object = focus_earth
    cams["final"].data.dof.focus_object = focus_earth

    # Contraintes de suivi
    for cname in ["wide", "earth_close", "sunrise", "travel", "impact", "final"]:
        tr = cams[cname].constraints.new('TRACK_TO')
        tr.target = earth
        tr.track_axis = 'TRACK_NEGATIVE_Z'
        tr.up_axis = 'UP_Y'

    tr_moon = cams["moon_orbit"].constraints.new('TRACK_TO')
    tr_moon.target = moon
    tr_moon.track_axis = 'TRACK_NEGATIVE_Z'
    tr_moon.up_axis = 'UP_Y'

    tr_met1 = cams["meteor_drama"].constraints.new('TRACK_TO')
    tr_met1.target = meteor
    tr_met1.track_axis = 'TRACK_NEGATIVE_Z'
    tr_met1.up_axis = 'UP_Y'

    tr_met2 = cams["meteor_follow"].constraints.new('COPY_LOCATION')
    tr_met2.target = meteor
    tr_met2.use_offset = True

    tr_met3 = cams["meteor_follow"].constraints.new('TRACK_TO')
    tr_met3.target = meteor
    tr_met3.track_axis = 'TRACK_NEGATIVE_Z'
    tr_met3.up_axis = 'UP_Y'

    # Animation traveling camera (orbite caméra)
    travel = cams["travel"]
    travel.location = (0, -10.5, 4.2)
    travel.keyframe_insert(data_path='location', frame=420)
    travel.location = (9.0, -1.5, 3.4)
    travel.keyframe_insert(data_path='location', frame=620)

    # Caméra finale doucement reculée
    final = cams["final"]
    final.location = (11.0, -9.0, 5.0)
    final.keyframe_insert(data_path='location', frame=1180)
    final.location = (19.0, -18.0, 9.0)
    final.keyframe_insert(data_path='location', frame=1440)

    # Timeline markers = cut caméra
    scene.camera = cams["wide"]
    add_camera_marker(scene, 1, cams["wide"], "SHOT_01_WIDE")
    add_camera_marker(scene, 160, cams["earth_close"], "SHOT_02_EARTH_CLOSE")
    add_camera_marker(scene, 300, cams["moon_orbit"], "SHOT_03_MOON")
    add_camera_marker(scene, 420, cams["sunrise"], "SHOT_04_SUNRISE")
    add_camera_marker(scene, 520, cams["travel"], "SHOT_05_TRAVEL")
    add_camera_marker(scene, 760, cams["meteor_drama"], "SHOT_06_METEOR_INTRO")
    add_camera_marker(scene, 900, cams["meteor_follow"], "SHOT_07_METEOR_FOLLOW")
    add_camera_marker(scene, 1120, cams["impact"], "SHOT_08_IMPACT")
    add_camera_marker(scene, 1220, cams["final"], "SHOT_09_FINAL")


def smooth_interpolation_all_actions():
    for action in bpy.data.actions:
        for fcurve in action.fcurves:
            for kp in fcurve.keyframe_points:
                if kp.interpolation != 'LINEAR':
                    kp.interpolation = 'BEZIER'


# ============================================================
# MAIN
# ============================================================
def main():
    scene = bpy.context.scene
    clear_scene()

    # Collections
    col_master = bpy.context.scene.collection
    col_planets = ensure_collection("COL_Planets", col_master)
    col_lights = ensure_collection("COL_Lights", col_master)
    col_vfx = ensure_collection("COL_VFX", col_master)
    col_space = ensure_collection("COL_Space", col_master)

    setup_render(scene)
    setup_world(scene)

    earth, clouds, atmosphere = create_earth_system(col_planets)
    moon, moon_orbit = create_moon(col_planets, earth)
    sun_light, sun_mesh = create_sun(col_lights)
    create_space_background(col_space)
    meteor, trail, explosion = create_meteor_and_fx(col_vfx, earth)

    setup_cameras(scene, earth, moon, meteor)
    smooth_interpolation_all_actions()

    scene.frame_set(1)
    print("\n=== CINEMATIC SPACE SCENE CREATED ===")
    print("Frames:", scene.frame_start, "->", scene.frame_end)
    print("FPS:", scene.render.fps)
    print("Durée (sec):", CONFIG['duration_seconds'])
    print("\nA faire ensuite:")
    print("1) Remplacer les chemins dans ASSET_PATHS pour les textures/HDRI.")
    print("2) Vérifier les caméras dans la timeline (markers de plans).")
    print("3) Choisir un dossier de sortie dans Output Properties.")
    print("4) Render > Render Animation.")


if __name__ == "__main__":
    main()
