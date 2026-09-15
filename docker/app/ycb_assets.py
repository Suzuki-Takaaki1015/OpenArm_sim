"""Shared YCB catalog for both robot versions; no downloads at runtime."""
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get('OPENARM_YCB_ROOT', '/opt/openarm/models/ycb'))
CATALOG = json.loads((ROOT / 'catalog.json').read_text()) if (ROOT / 'catalog.json').is_file() else []

def items():
    result = {}
    for entry in CATALOG:
        if not entry['available']:
            continue
        folder = ROOT / entry['name']
        model = json.loads((folder / 'model.json').read_text())
        geoms = [dict(type='mesh', mesh=str(folder / model['visual']), pos=[0,0,0],
                      rgba=[1,1,1,1] if model.get('texture') else [.65,.7,.75,1], collision=False,
                      texture=str(folder / model['texture']) if model.get('texture') else None)]
        geoms += [dict(type='mesh', mesh=str(folder / filename), pos=[0,0,0],
                       rgba=[0,0,0,0], collision=True) for filename in model['collision']]
        result[entry['key']] = dict(id='openarm_'+entry['key'], label=entry['label'],
            mass=entry['mass_kg'], size=model['size'], half_height=model['size'][2]/2,
            geoms=geoms, ycb=True)
    return result

def set_visibility(model, geom_id, description, enabled):
    """Materials override geom colour: remove the material while hidden."""
    import mujoco
    model.geom_rgba[geom_id] = description['rgba'] if enabled else [0,0,0,0]
    if description.get('texture'):
        name=mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_GEOM,geom_id)+'_material'
        model.geom_matid[geom_id]=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_MATERIAL,name) if enabled else -1
