"""Flatten pinned official pedestal model without changing its kinematics."""
from pathlib import Path
import xml.etree.ElementTree as E
import mujoco
root=Path('/opt/openarm/models/v2')
m=mujoco.MjModel.from_xml_path(str(root/'pedestal/openarm_pedestal.xml'))
out=root/'simulation_robot.xml'
mujoco.mj_saveLastXML(str(out),m)
tree=E.parse(out);x=tree.getroot();x.find('compiler').set('meshdir',str(root/'assets'))
# mj_saveLastXML can emit anonymous nested defaults for attached models.
for parent in list(x.iter('default')):
 for child in list(parent.findall('default')):
  if not child.get('class'):
   for item in list(child):parent.append(item)
   parent.remove(child)
w=x.find('worldbody');base=E.Element('body',name='openarm_body_link0')
for child in list(w):w.remove(child);base.append(child)
w.append(base)
for side in ('left','right'):
 b=x.find(f".//body[@name='openarm_{side}_ee_base_link']")
 # Control frame only: local +Z points out along the fingers, like the v1 hand.
 E.SubElement(b,'body',name=f'openarm_{side}_hand',quat='0 1 0 0')
tree.write(out,encoding='unicode')
# Same environment lighting and ground for both versions.
scene=E.parse(root.parent/'v1/scene.xml');scene.find('include').set('file',out.name)
scene.write(root/'scene.xml',encoding='unicode')
