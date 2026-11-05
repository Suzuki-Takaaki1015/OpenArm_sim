"""Build a matching MJCF, URDF and SRDF for the robot without its LiDAR."""
import xml.etree.ElementTree as ET
from pathlib import Path

LINKS = {'mid360s_mount', 'mid360s_bracket', 'mid360s_link'}

def detached(path):
    path = Path(path)
    return path.with_name(path.stem + '_no_lidar' + path.suffix)

def build(robot, config):
    model = ET.parse(robot)
    base = model.find("worldbody/body[@name='openarm_body_link0']")
    for name in ('mid360s_mount', 'mid360s_bracket'):
        base.remove(base.find(f"body[@name='{name}']"))
    for mesh in list(model.findall('asset/mesh')):
        if mesh.get('name') in ('lidar_visual','lidar_collision','lidar_bracket'):
            model.find('asset').remove(mesh)
    for exc in list(model.findall('contact/exclude')):
        if {exc.get('body1'),exc.get('body2')} & LINKS:
            model.find('contact').remove(exc)
    model.write(detached(robot),encoding='utf-8')
    path = robot.with_name('simulation_scene.xml')
    scene = ET.parse(path)
    include = scene.find(f"include[@file='{robot.name}']")
    if include is None:raise ValueError(f'Missing scene include: {robot.name}')
    include.set('file',detached(robot).name)
    scene.write(detached(path),encoding='utf-8')
    path = config/'openarm.urdf'
    urdf = ET.parse(path)
    for item in list(urdf.getroot()):
        if (item.tag=='link' and item.get('name') in LINKS or
            item.tag=='joint' and any(n.get('link') in LINKS for n in item)):
            urdf.getroot().remove(item)
    urdf.write(detached(path),encoding='utf-8')
    path = config/'openarm.srdf'
    srdf = ET.parse(path)
    for exc in list(srdf.findall('disable_collisions')):
        if {exc.get('link1'),exc.get('link2')} & LINKS:srdf.getroot().remove(exc)
    srdf.write(detached(path),encoding='utf-8')
