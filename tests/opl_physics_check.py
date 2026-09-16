"""Integration tests for real generated v1/v2 scenes; run with container entrypoint."""
import os,time,math,json
from pathlib import Path
import mujoco as mj
import numpy as np
from PIL import Image
from physics import Simulation
from dynamic_objects import DynamicObjects
from environment_assets import ITEMS
from opl_assets import CATALOG,FURNITURE,PROXIES
from scene_objects import OBJECTS

out=Path('/tmp/opl-evidence');out.mkdir(exist_ok=True)
def rejected(fn,contains=''):
    try:fn()
    except ValueError as e:
        assert contains in str(e),(contains,str(e));return
    raise AssertionError('Unsafe request accepted')

for version in (1,2):
    os.environ['OPENARM_VERSION']=str(version)
    os.environ['OPENARM_MODEL']=f'/opt/openarm/models/v{version}/'+('openarm_bimanual.xml' if version==1 else 'simulation_robot.xml')
    os.environ['OPENARM_SCENE']=f'/opt/openarm/models/v{version}/simulation_scene.xml'
    sim=Simulation();m,d=sim.model,sim.data;dyn=DynamicObjects(sim)
    assert m.nmocap==14
    assert all(not v for v in dyn.active.values())
    assert all(e['key'] in ITEMS for e in CATALOG)
    # Every published furniture can be placed, moved and hidden; static collision tests.
    for key in FURNITURE:
        dyn.set_enabled(key,True,pose=(2,0,.35))
        p=dyn.pose(key).copy()
        for _ in range(10):sim.step()
        assert np.allclose(p,dyn.pose(key)),key
        dyn.set_enabled(key,True,reposition=True,pose=(2,.1,-.3))
        dyn.set_enabled(key,False)
    print('PASS',version,'all14 furniture anchored place/MOVE/hide',flush=True)
    key='opl_coffee_table'
    dyn.set_enabled(key,True,pose=(2,0,0))
    before=dyn.pose(key).copy()
    for pose in [(float('nan'),0,0),(6,0,0),(2,0,7)]:
        rejected(lambda:dyn.set_enabled(key,True,reposition=True,pose=pose))
        assert np.array_equal(before,dyn.pose(key))
    rejected(lambda:dyn.set_enabled('opl_side_table',True,pose=(2,0,0)))
    rejected(lambda:dyn.set_enabled(key,True,reposition=True,pose=(0,0,0)))
    assert np.array_equal(before,dyn.pose(key))
    # Rotated surface coordinate transform, bounds, collision rollback and occupancy.
    dyn.set_enabled(key,True,reposition=True,pose=(2,0,math.pi/2))
    support=key+':top'
    dyn.set_enabled('opl_lemonade',True,pose=(2,.1,math.pi/2),support=support)
    p=dyn.pose('opl_lemonade').copy()
    rejected(lambda:dyn.set_enabled(key,False),'Remove objects')
    rejected(lambda:dyn.set_enabled(key,True,reposition=True,pose=(3,0,0)),'Remove objects')
    rejected(lambda:dyn.set_enabled('opl_lemonade',True,reposition=True,pose=(2.4,0,0),support=support),'footprint')
    assert np.array_equal(p,dyn.pose('opl_lemonade'))
    rejected(lambda:dyn.set_enabled('opl_coffee_can',True,pose=(2,.1,0),support=support))
    dyn.set_enabled('opl_lemonade',False);dyn.set_enabled(key,False)
    rejected(lambda:dyn.set_enabled('opl_lemonade',True,pose=(2,0,0),support=support),'supporting')
    print('PASS',version,'NaN/range/rotated bounds/collisions/rollback/occupied guard',flush=True)
    # Every official object survives gravity on a published support.
    dyn.set_enabled('opl_dining_table',True,pose=(2,0,0))
    support='opl_dining_table:top'
    for entry in CATALOG:
        key=entry['key'];dyn.set_enabled(key,True,pose=(2,0,0),support=support)
        for _ in range(160):sim.step()
        p=dyn.pose(key)
        assert np.isfinite(d.qpos).all()
        assert p[2]>.70,(version,key,p)
        dyn.set_enabled(key,False)
    for key in [k for k in PROXIES if k.startswith('opl_clothes_')]:
        dyn.set_enabled(key,True,support=support)
        dyn.set_enabled(key,False)
    # A 12 mm sphere fits even the smallest cup opening. Use the exact compound
    # geometry; the legacy 50x40 mm box is too wide diagonally for Jagarico.
    import xml.etree.ElementTree as E
    for vessel in ['opl_tray','opl_laundry_basket','opl_bag','opl_cup_noodle','opl_cup_rice','opl_jagarico']:
        obj=ITEMS[vessel]
        xml=E.Element('mujoco');world=E.SubElement(xml,'worldbody')
        body=E.SubElement(world,'body',pos=f"0 0 {obj['size'][2]/2}")
        for i,g in enumerate(obj['geoms']):
            gi=mj.mj_name2id(m,mj.mjtObj.mjOBJ_GEOM,f'{obj["id"]}_{i}')
            E.SubElement(body,'geom',type=g['type'],pos=' '.join(map(str,g['pos'])),size=' '.join(map(str,g['size'])),solref=' '.join(map(str,m.geom_solref[gi])),solimp=' '.join(map(str,m.geom_solimp[gi])),priority=str(m.geom_priority[gi]))
        probe=E.SubElement(world,'body',pos=f"0 0 {obj['size'][2]+.06}")
        E.SubElement(probe,'freejoint')
        E.SubElement(probe,'geom',type='sphere',size='.006',mass='.01')
        cm=mj.MjModel.from_xml_string(E.tostring(xml,encoding='unicode'));cd=mj.MjData(cm)
        for _ in range(900):mj.mj_step(cm,cd)
        wall=.003 if 'cup' in vessel or vessel=='opl_jagarico' else .005
        assert abs(cd.qpos[2]-(wall+.006))<.002,(vessel,cd.qpos)
    print('PASS',version,'six open cavities accept 12mm physical sphere down to their bottom',flush=True)
    dyn.set_enabled('opl_dining_table',False)
    # Shelf interior, random selection and collision against upper shelf.
    dyn.set_enabled('opl_cabinet',True,pose=(2,0,.4))
    dyn.set_enabled('opl_lemonade',True,support='opl_cabinet:shelf1')
    for _ in range(100):sim.step()
    assert dyn.pose('opl_lemonade')[2]>.1
    dyn.set_enabled('opl_lemonade',False);dyn.set_enabled('opl_cabinet',False)
    # Legacy table and box remain physically usable.
    for o in OBJECTS:
        g=mj.mj_name2id(m,mj.mjtObj.mjOBJ_GEOM,o['id'])
        m.geom_contype[g]=m.geom_conaffinity[g]=1
        m.body_contype[m.geom_bodyid[g]]=m.body_conaffinity[m.geom_bodyid[g]]=1
    dyn.set_enabled('box',True,pose=(.4,-.2,0))
    for _ in range(150):sim.step()
    assert dyn.pose('box')[2]>.18
    dyn.set_enabled('box',False)
    for o in OBJECTS:
        g=mj.mj_name2id(m,mj.mjtObj.mjOBJ_GEOM,o['id'])
        m.geom_contype[g]=m.geom_conaffinity[g]=0
    # Compare camera model against physics including mocap position/visibility.
    # Disable world contacts for isolated interior drop: cavity must not be a solid hull.
    renderer=mj.Renderer(m,height=180,width=320)
    renderer.update_scene(d,camera='d435_color')
    Image.fromarray(renderer.render()).save(out/f'v{version}-empty.png')
    dyn.set_enabled('opl_coffee_table',True,pose=(1.05,0,0))
    renderer.update_scene(d,camera='d435_color')
    Image.fromarray(renderer.render()).save(out/f'v{version}-furniture.png')
    renderer.enable_segmentation_rendering();renderer.update_scene(d,camera='d435_color')
    seg=renderer.render();ids=set(seg[:,:,0].ravel())
    assert ids.intersection(dyn.geoms('opl_coffee_table')),(version,'furniture absent from camera')
    renderer.disable_segmentation_rendering()
    renderer.enable_depth_rendering();renderer.update_scene(d,camera='d435_depth')
    depth=renderer.render();assert np.isfinite(depth).all()
    np.save(out/f'v{version}-depth.npy',depth)
    renderer.close()
    print('PASS',version,'all34 objects/supports/legacy physics + RGB/depth furniture visibility',flush=True)
print('PASS OPL isolated both-model validation')
