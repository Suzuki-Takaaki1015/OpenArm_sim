"""Versioned JSON scene layouts. No pickle, paths, executable data or overwrites."""
import copy
import json
import math
import os
import re
from pathlib import Path

MAX_BYTES = 256 * 1024


def decode(text):
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Preset exceeds 256 KiB')
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def bad(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=bad)


def keys(value, expected, label):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError(label + ': unknown or missing keys')


def pose(value, active, label):
    if type(value) is not list or len(value) != 7 or any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError(label + ': pose requires seven finite numbers (xyz, quaternion wxyz)')
    limit = 5 if active else 256
    if any(abs(x) > limit for x in value[:3]):
        raise ValueError(label + ': position outside allowed range')
    if abs(sum(x*x for x in value[3:])-1) > 1e-5:
        raise ValueError(label + ': quaternion must be normalized')


def validate(document, items, tables, version):
    keys(document, ('schema', 'version', 'robot_model', 'tables', 'objects'), 'preset')
    if document['schema'] != 'openarm.scene' or type(document['version']) is not int or document['version'] != 1:
        raise ValueError('Unsupported scene schema/version')
    if document['robot_model'] not in ('1', '2') or document['robot_model'] != version:
        raise ValueError('Robot model mismatch: use a preset saved on this model')
    keys(document['tables'], [t['id'] for t in tables], 'tables')
    for table in tables:
        state = document['tables'][table['id']]
        keys(state, ('enabled', 'pose'), table['id'])
        if type(state['enabled']) is not bool:
            raise ValueError('Table enabled must be boolean')
        pose(state['pose'], True, table['id'])
        # The existing worktable is a fixed world geom, not a movable body.
        if state['pose'] != table['position'] + [1, 0, 0, 0]:
            raise ValueError('Fixed worktable pose is incompatible with this scene')
    keys(document['objects'], items, 'objects/catalog')
    for key, spec in items.items():
        state = document['objects'][key]
        keys(state, ('enabled', 'pose', 'support'), key)
        if type(state['enabled']) is not bool:
            raise ValueError(key + ': enabled must be boolean')
        pose(state['pose'], state['enabled'], key)
        support = state['support']
        if spec.get('furniture'):
            if support is not None:
                raise ValueError(key + ': furniture cannot have a support')
            if state['enabled'] and (abs(state['pose'][2]-spec['half_height']) > 1e-5 or max(abs(x) for x in state['pose'][4:6]) > 1e-5):
                raise ValueError(key + ': furniture must stand upright on the floor')
        elif support is not None:
            if type(support) is not str:
                raise ValueError(key + ': invalid support type')
            if support == 'worktable':
                enabled = all(t['enabled'] for t in document['tables'].values())
            else:
                parts = support.split(':')
                if len(parts) != 2 or parts[0] not in items or parts[1] not in [s['name'] for s in items[parts[0]].get('surfaces', [])]:
                    raise ValueError(key + ': unknown support')
                enabled = document['objects'][parts[0]]['enabled']
            if state['enabled'] and not enabled:
                raise ValueError(key + ': support is disabled')
        elif state['enabled']:
            raise ValueError(key + ': active object requires a support association')
    return copy.deepcopy(document)


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory or '/workspaces/OpenArm_dev/scene_presets')

    def path(self, name):
        if type(name) is not str or not re.fullmatch(r'[\w\- ]{1,64}', name, re.UNICODE) or not name.strip():
            raise ValueError('名前は1〜64文字の文字・数字・空白・_・-にしてください')
        return self.directory / (name + '.json')

    def save(self, name, document):
        path = self.path(name)
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.directory.is_symlink():
            raise ValueError('Preset directory cannot be a symbolic link')
        content = json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
        if len(content) > MAX_BYTES:
            raise ValueError('Preset too large')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink()
            raise
        return path

    def load(self, name):
        path = self.path(name)
        if path.is_symlink():
            raise ValueError('Preset symbolic links are not supported')
        with path.open('rb') as stream:
            data = stream.read(MAX_BYTES+1)
        if len(data) > MAX_BYTES:
            raise ValueError('Preset too large')
        return decode(data.decode('utf-8'))

    def names(self):
        return sorted(p.stem for p in self.directory.glob('*.json') if p.is_file() and not p.is_symlink())
