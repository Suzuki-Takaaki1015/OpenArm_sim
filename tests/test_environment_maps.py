"""A competition environment keeps its map and localization choice across switches."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'docker/app'))
import happy_navigation as nav
import room_layout as rooms

class EnvironmentMaps(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.active = root/'active.json'
        for mock in (patch.object(rooms,'ACTIVE',self.active),
                     patch.multiple(nav,WORK=root,MAPS=root/'maps',MODE=root/'mode.json')):
            mock.start()
            self.addCleanup(mock.stop)
        self.layout = dict(version=1,items=[rooms.item('wall',2,0)])
        rooms.write(self.active,self.layout)

    def map(self,directory):
        directory.mkdir(parents=True)
        (directory/'room.id').write_text(nav.room_id())
        (directory/'map.yaml').write_text('image: map.pgm')
        return directory/'map.yaml'

    def test_library_label_preserves_legacy_map_and_new_mode_is_per_layout(self):
        a=nav.room_id()
        old_map=self.map(nav.MAPS/'arena')
        nav.MODE.write_text(json.dumps({'map':'arena','room':a}))
        rooms.write(self.active,dict(self.layout,library_name='予選'))
        self.assertEqual(nav.selected(),old_map)
        rooms.write(self.active,dict(version=1,items=[]))
        self.assertIsNone(nav.selected())
        self.assertEqual(nav.map_paths(nav.room_id()),{})
        new_map=self.map(nav.space(nav.room_id())/'maps'/'arena')
        nav.choose('arena')
        self.assertEqual(nav.selected(),new_map)
        rooms.write(self.active,self.layout)
        nav.choose(None)
        self.assertIsNone(nav.selected())
        rooms.write(self.active,dict(version=1,items=[]))
        self.assertEqual(nav.selected(),new_map)
