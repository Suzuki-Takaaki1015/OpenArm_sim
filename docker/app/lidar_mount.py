"""Project fixed mount; official MID-360S bottom/optical datums in metres."""
import json, math
from pathlib import Path
import xml.etree.ElementTree as E
ASSETS=Path(__file__).with_name('lidar_assets')
def config():return json.loads(Path(__file__).with_name('lidar_config.json').read_text())
def prepare_robot(path):
    cfg=config();tree=E.parse(path);root=tree.getroot();assets=root.find('asset')
    parent=root.find("worldbody/body[@name='openarm_body_link0']")
    if parent is None:raise ValueError('Expected OpenArm base')
    for node in list(assets):
        if node.get('name','').startswith('lidar_'):assets.remove(node)
    for node in list(parent):
        if node.get('name','').startswith(('mid360s_','lidar_')):parent.remove(node)
    for name,file in [('visual','mid360s.obj'),('collision','mid360s_collision.obj'),('bracket','bracket.obj')]:
        E.SubElement(assets,'mesh',name='lidar_'+name,file=str(ASSETS/file))
    vec=lambda v:' '.join(str(x) for x in v)
    a=math.radians(cfg['mount_pitch_deg'])/2
    mount=E.SubElement(parent,'body',name='mid360s_mount',pos=vec(cfg['mount_position_m']),quat=vec([math.cos(a),0,math.sin(a),0]))
    for purpose,mesh in [('visual','visual'),('collision','collision')]:
        E.SubElement(mount,'geom',name='lidar_housing_'+purpose,type='mesh',mesh='lidar_'+mesh,material='matte_black',rgba='.25 .25 .28 1' if purpose=='visual' else '0 0 0 0',**{'class':purpose})
    E.SubElement(mount,'body',name='mid360s_link',pos=vec(cfg['optical_offset_m']))
    bracket=E.SubElement(parent,'body',name='mid360s_bracket')
    for purpose in ('visual','collision'):
        E.SubElement(bracket,'geom',name='lidar_bracket_'+purpose,type='mesh',mesh='lidar_bracket',material='matte_black',rgba='.3 .3 .32 1' if purpose=='visual' else '0 0 0 0',**{'class':purpose})
    contact=root.find('contact')
    if contact is None:contact=E.SubElement(root,'contact')
    if contact.find("exclude[@name='lidar_mount_interface']") is None:
        E.SubElement(contact,'exclude',name='lidar_mount_interface',body1='mid360s_mount',body2='mid360s_bracket')
    tree.write(path,encoding='unicode')
