import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'docker/app'))
from room_layout import descriptions, item, read, validate, write
from happy_navigation import room_id


class TabletopTests(unittest.TestCase):
    def setUp(self):
        self.table = dict(item('table',1.8,-.5),yaw=90,
                          objects=[dict(kind='bottle',x=.14,y=.21,yaw=32.)])
        self.room = dict(version=1,items=[self.table])

    def test_rotated_support_and_library_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'room.json'
            write(path,self.room)
            self.assertEqual(read(path),self.room)
            asset,p = descriptions(read(path))['happy_room_000_prop_000']
            for actual, expected in zip(p,[1.59,-.36,.74+asset['half_height'],
                                            math.cos(math.radians(61)),0,0,math.sin(math.radians(61))]):
                self.assertAlmostEqual(actual,expected)

    def test_no_overhang_no_overlap(self):
        self.table['objects'].append(dict(kind='box',x=.14,y=.21,yaw=45))
        with self.assertRaises(ValueError): validate(self.room)
        self.table['objects'][1].update(x=.59,y=0)
        with self.assertRaises(ValueError): validate(self.room)
        self.table['objects'][1].update(x=.54)
        validate(self.room)
        self.table['objects'][1]['x']=float('nan')
        with self.assertRaises(ValueError): validate(self.room)
        self.table['objects'].pop()
        self.table['kind']='chair'
        with self.assertRaises(ValueError): validate(self.room)

    def test_move_objects_reuses_navigation_map(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'room.json'
            with patch('room_layout.ACTIVE',path):
                write(path,self.room)
                old = room_id()
                self.table.pop('objects')
                write(path,self.room)
                self.assertEqual(room_id(),old)
                self.table['x'] += .2
                write(path,self.room)
                self.assertNotEqual(room_id(),old)
