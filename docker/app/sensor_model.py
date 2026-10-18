"""Sensor-only model: retain dynamics layout but load only visible scene assets."""
import os
import mujoco
from environment_assets import ITEMS

def active_objects(snapshot):
    return frozenset(key for key in ITEMS if snapshot['objects'][key]['enabled'])

def load_sensor_model(snapshot, textures=True):
    mujoco.mj_setCacheCapacity(mujoco.mj_getCache(), 64 * 1024 * 1024)
    spec=mujoco.MjSpec.from_file(os.environ['OPENARM_SCENE'])
    active=active_objects(snapshot)
    omitted={f'{obj["id"]}_{i}' for key,obj in ITEMS.items() for i,g in enumerate(obj['geoms'])
             if key not in active or g.get('collision',False)}
    for geom in list(spec.geoms):
        if geom.name in omitted:spec.delete(geom)
    referenced={g.meshname for g in spec.geoms if g.meshname}
    for mesh in list(spec.meshes):
        if mesh.name not in referenced:spec.delete(mesh)
    if not textures:
        for texture in spec.textures:
            texture.file='';texture.cubefiles=['']*6
            texture.builtin=mujoco.mjtBuiltin.mjBUILTIN_FLAT
            texture.width=4;texture.height=4
    model=spec.compile()
    return model,active
