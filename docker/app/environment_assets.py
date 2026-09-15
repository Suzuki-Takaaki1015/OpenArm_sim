"""Scene asset definitions. SI units. Bottle is an approximate rigid, filled 500 mL bottle."""
import json, math, copy
from pathlib import Path
import xml.etree.ElementTree as E
import numpy as np
from ycb_assets import items

ITEMS={
 'box':{'id':'openarm_grasp_box','label':'直方体','mass':0.10,'half_height':0.04,
        'geoms':[{'type':'box','size':[0.025,0.02,0.04],'pos':[0,0,0],'rgba':[0.95,0.55,0.12,1]}]},
 'bottle':{'id':'openarm_grasp_bottle','label':'500 mL PETボトル（近似）','mass':0.525,'half_height':0.105,
        'geoms':[{'type':'cylinder','size':[0.0325,0.085],'pos':[0,0,-0.02],'rgba':[0.3,0.65,0.85,1]},
                 {'type':'ellipsoid','size':[0.0325,0.0325,0.025],'pos':[0,0,0.065],'rgba':[0.3,0.65,0.85,1]},
                 {'type':'cylinder','size':[0.014,0.014],'pos':[0,0,0.088],'rgba':[0.3,0.65,0.85,1]},
                 {'type':'cylinder','size':[0.015,0.008],'pos':[0,0,0.102],'rgba':[0.1,0.25,0.65,1]}]}}

ITEMS['box_left']=copy.deepcopy(ITEMS['box'])
ITEMS['box_left']['id']='openarm_grasp_box_left'
ITEMS['box_left']['label']='左手用直方体'

ITEMS.update(items())

def camera_config():
    from camera_mount import config
    return config()

def rotation(rpy):
    r,p,y=rpy;cr,sr=math.cos(r),math.sin(r);cp,sp=math.cos(p),math.sin(p);cy,sy=math.cos(y),math.sin(y)
    return np.array([[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],[sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]])

def add_assets(scene_path):
    tree=E.parse(scene_path);world=tree.find('worldbody')
    assets=tree.find('asset')
    if assets is None:assets=E.SubElement(tree.getroot(),'asset')
    vec=lambda x:' '.join(str(v) for v in x)
    for index,(key,obj) in enumerate(ITEMS.items()):
        body=E.SubElement(world,'body',name=obj['id'],pos=f'{index} 0 -5',gravcomp='1')
        E.SubElement(body,'freejoint',name=obj['id']+'_free')
        # Explicit inertia avoids making total mass depend on overlapping visual primitives.
        mass=obj['mass'];inertia=[mass*0.004,mass*0.004,mass*0.001] if key=='bottle' else [mass*(.04**2+.08**2)/12,mass*(.05**2+.08**2)/12,mass*(.05**2+.04**2)/12]
        if 'size' in obj:
            x,y,z=obj['size'];inertia=[mass*(y*y+z*z)/12,mass*(x*x+z*z)/12,mass*(x*x+y*y)/12]
        E.SubElement(body,'inertial',pos='0 0 0',mass=str(mass),diaginertia=vec(inertia))
        for i,g in enumerate(obj['geoms']):
            name=f'{obj["id"]}_{i}'
            attrs=dict(name=name,type=g['type'],pos=vec(g['pos']),rgba='0 0 0 0',contype='0',conaffinity='0',condim='4',friction='1 0.01 0.001')
            if g['type']=='mesh':
                E.SubElement(assets,'mesh',name=name+'_mesh',file=g['mesh'])
                attrs['mesh']=name+'_mesh';attrs['group']='3' if g['collision'] else '2'
                if g.get('texture'):
                    E.SubElement(assets,'texture',name=name+'_texture',type='2d',file=g['texture'])
                    E.SubElement(assets,'material',name=name+'_material',texture=name+'_texture',rgba='1 1 1 1',specular='0.1')
                    # Material is enabled together with the object's visibility at runtime.
            else:attrs['size']=vec(g['size'])
            E.SubElement(body,'geom',**attrs)
    cfg=camera_config();R=rotation(cfg['rpy_rad']);xyaxes=vec(list(-R[:,1])+list(R[:,2]))
    for channel in ('color','depth'):
        offset=R@np.array(cfg['color_offset_m']) if channel=='color' else np.zeros(3)
        E.SubElement(world,'camera',name='d435_'+channel,pos=vec(np.array(cfg['position_m'])+offset),xyaxes=xyaxes,fovy=str(cfg[channel]['vertical_fov_deg']))
    tree.write(scene_path,encoding='unicode')
