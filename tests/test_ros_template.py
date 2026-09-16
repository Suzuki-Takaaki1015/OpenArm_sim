"""Host-only generator regression checks; no ROS or third-party dependencies."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('generator', Path(__file__).resolve().parents[1] / 'docker/scripts/create_ros_package.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class GeneratorTests(unittest.TestCase):
    def test_preserves_member_files_and_rejects_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = generator.create_package('member_reader', root)
            source = package / 'member_reader/read_example.py'
            compile(source.read_text(), str(source), 'exec')
            source.write_text('# member changes\n')
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with self.assertRaises(FileExistsError):
                generator.create_package('member_reader', root)
            self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()})
            for name in ('../outside', '/absolute', 'bad-name', 'class', 'json', 'rclpy', 'Upper'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    generator.create_package(name, root)

    def test_existing_file_and_broken_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'src/file_entry').write_text('keep')
            (root / 'src/link_entry').symlink_to(root / 'missing')
            for name in ('file_entry', 'link_entry'):
                with self.assertRaises(FileExistsError):
                    generator.create_package(name, root)
            self.assertEqual((root / 'src/file_entry').read_text(), 'keep')
            self.assertTrue((root / 'src/link_entry').is_symlink())

    def test_symlinked_src_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'elsewhere').mkdir()
            (root / 'src').symlink_to(root / 'elsewhere', target_is_directory=True)
            with self.assertRaises(ValueError):
                generator.create_package('member_reader', root)
            self.assertEqual(list((root / 'elsewhere').iterdir()), [])


if __name__ == '__main__':
    unittest.main()
