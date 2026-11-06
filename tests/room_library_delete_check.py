"""Mode-3 Tk integration test. Run with xvfb-run -a python in the mobile image."""
import copy
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import room_editor
from room_layout import item, write


class RoomLibraryDelete(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.rooms = root / 'rooms'
        self.active = self.rooms / '.active.json'
        self.name = '大会・予選'
        self.saved = self.rooms / (self.name + '.json')
        self.other = self.rooms / '決勝.json'
        self.map = root / 'navigation' / 'map.yaml'
        self.map.parent.mkdir()
        self.map.write_text('image: map.pgm')
        self.doc = dict(version=1, items=[item('table', 2, 1)])
        write(self.saved, self.doc)
        write(self.active, dict(self.doc, library_name=self.name))
        write(self.other, dict(version=1, items=[]))
        paths = patch.multiple(room_editor, ROOMS=self.rooms, ACTIVE=self.active)
        paths.start()
        self.addCleanup(paths.stop)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        self.editor = room_editor.RoomEditor(self.root)
        self.root.update()

    def choose(self, name):
        self.editor.library.set(name)
        self.editor.library.event_generate('<<ComboboxSelected>>')
        self.root.update()

    def test_active_room_and_unsaved_edits_survive_deleting_the_saved_copy(self):
        active_before = self.active.read_bytes()
        other_before = self.other.read_bytes()
        self.editor.remember()
        self.editor.items.append(item('chair', 3, 2))
        self.editor.select(1)
        self.editor.inputs['x'].set('3.7')  # Include an uncommitted text field.
        draft = copy.deepcopy(self.editor.items)
        self.choose(self.name)
        with patch.object(room_editor.messagebox, 'askyesno', return_value=False) as dialog:
            self.editor.delete_room_button.invoke()
            self.assertIn(self.name, dialog.call_args.args[1])
            self.assertEqual(dialog.call_args.kwargs['default'], 'no')
        self.assertTrue(self.saved.exists())
        with patch.object(room_editor.messagebox, 'askyesno', return_value=True):
            self.editor.delete_room_button.invoke()
        self.assertFalse(self.saved.exists())
        self.assertEqual(self.editor.library['values'], ('決勝',))
        self.assertEqual(self.editor.library_name.get(), '')
        self.assertTrue(self.editor.delete_room_button.instate(['disabled']))
        self.assertIn('ライブラリ保存なし', self.editor.active_label.get())
        self.assertEqual(self.editor.items, draft)
        self.assertEqual(self.editor.inputs['x'].get(), '3.7')
        self.assertEqual(self.editor.editing_name, '')
        self.assertTrue(self.editor.history)
        self.assertEqual(self.active.read_bytes(), active_before)
        self.assertEqual(self.other.read_bytes(), other_before)
        self.assertEqual(self.map.read_text(), 'image: map.pgm')
        self.editor.destroy()
        self.editor = room_editor.RoomEditor(self.root)
        self.assertEqual(self.editor.items, self.doc['items'])
        self.assertEqual(self.editor.library_name.get(), '')
        self.assertIn('ライブラリ保存なし', self.editor.active_label.get())

    def test_deleting_another_room_through_the_real_confirmation_dialog(self):
        self.choose('決勝')
        self.root.update_idletasks()
        result = []
        def confirm():
            # On Linux Tk creates this widget path relative to the dialog parent.
            try:
                self.root.tk.call(str(self.editor) + '.__tk__messagebox.yes', 'invoke')
                result.append(True)
            except tk.TclError:
                self.root.tk.call('set', '::tk::Priv(button)', 'no')
        self.root.after(150, confirm)
        self.editor.delete_room_button.invoke()
        self.assertTrue(result)
        self.assertFalse(self.other.exists())
        self.assertTrue(self.saved.exists())
        self.assertEqual(self.editor.editing_name, self.name)
        self.assertEqual(self.editor.active_label.get(), '使用中：' + self.name)
        self.choose(self.name)
        with patch.object(room_editor.messagebox, 'askyesno', return_value=True):
            self.editor.delete_room_button.invoke()
        self.assertFalse(self.editor.library['values'])
        self.assertTrue(self.editor.delete_room_button.instate(['disabled']))

    def test_new_or_imported_draft_clears_the_old_deletion_target(self):
        for open_draft in [self.editor.clear, lambda: self.editor.replace_draft(self.doc, '')]:
            self.choose('決勝')
            open_draft()
            self.assertEqual(self.editor.library_name.get(), '')
            self.assertTrue(self.editor.delete_room_button.instate(['disabled']))
        self.assertTrue(self.other.exists())

    def test_changed_missing_hidden_and_linked_rooms(self):
        self.choose('決勝')
        def replace_room(*args, **kwargs):
            write(self.other, self.doc)
            return True
        with patch.object(room_editor.messagebox, 'askyesno', side_effect=replace_room):
            self.editor.delete_room_button.invoke()
        self.assertTrue(self.other.exists())
        self.assertIn('変更', self.editor.status.get())
        self.other.unlink()
        with patch.object(room_editor.messagebox, 'askyesno') as dialog:
            self.editor.delete_room_button.invoke()
            self.assertFalse(dialog.called)
        self.assertEqual(self.editor.library_name.get(), '')
        (self.rooms/'別名.json').symlink_to(self.saved)
        for name in ['別名', '.active', '../navigation/map']:
            self.editor.library_name.set(name)
            with patch.object(room_editor.messagebox, 'askyesno') as dialog:
                self.editor.delete_saved()
                self.assertFalse(dialog.called)
        self.assertTrue(self.active.is_file())
        self.assertTrue(self.saved.is_file())
        self.assertTrue((self.rooms/'別名.json').is_symlink())


if __name__ == '__main__':
    unittest.main()
