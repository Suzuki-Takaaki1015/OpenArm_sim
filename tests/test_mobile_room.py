import math
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'docker/app'))
from room_layout import compose, descriptions, item, read, validate, write

class MobileRoomTests(unittest.TestCase):
    def test_rotated_spawn_exclusion(self):
        wall = item('wall',0,1)
        validate(dict(version=1,items=[wall]))
        wall['yaw']=90
        with self.assertRaises(ValueError):
            validate(dict(version=1,items=[wall]))

    def test_invalid_dimensions_do_not_replace_saved_room(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'room.json'
            obj=item('chair',2,1)
            doc=dict(version=1,items=[obj])
            write(path,doc)
            obj['height']=math.nan
            with self.assertRaises(ValueError):write(path,doc)
            self.assertEqual(read(path)['items'][0]['height'],.83)

    def test_xml_and_collision_primitives_match(self):
        with tempfile.TemporaryDirectory() as folder:
            scene=Path(folder)/'base.xml'
            scene.write_text('<mujoco><include file="robot.xml"/><worldbody/></mujoco>')
            obj=item('table',1.5,-2)
            obj['yaw']=37
            room=dict(version=1,items=[obj])
            xml=ET.parse(compose(scene,room,folder))
            self.assertEqual(xml.find('include').get('file'),str(Path(folder)/'robot.xml'))
            geometry,pose=descriptions(room)['happy_room_000']
            body=xml.find('worldbody/body')
            self.assertEqual([float(v) for v in body.get('quat').split()],pose[3:])
            geoms=body.findall('geom')
            self.assertEqual(len(geoms),5)
            for geom,primitive in zip(geoms,geometry['geoms']):
                self.assertEqual(list(map(float,geom.get('size').split())),primitive['size'])
                self.assertEqual(list(map(float,geom.get('pos').split())),primitive['pos'])
