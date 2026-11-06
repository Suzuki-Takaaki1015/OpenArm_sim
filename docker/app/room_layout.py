"""Shared geometry and versioned storage for the mobile robot's rooms (SI, world frame)."""
import json
import math
import os
from pathlib import Path
from tabletop import PROPS, validate_objects, world_xy
import tempfile
import xml.etree.ElementTree as ET

ROOMS = Path('/workspaces/OpenArm_dev/rooms')
ACTIVE = ROOMS / '.active.json'
EMPTY = {'version': 1, 'items': []}
# Default full dimensions: local X length, local Y depth, floor-to-top height.
KINDS = {
    'wall': ('壁', (2.4, .12, 1.8), (.70, .73, .77, 1)),
    'table': ('机', (1.2, .7, .74), (.69, .46, .26, 1)),
    'chair': ('椅子', (.46, .46, .83), (.24, .48, .51, 1)),
    'cabinet': ('収納棚', (.9, .4, 1.2), (.50, .36, .27, 1)),
}
FIELDS = ('x', 'y', 'yaw', 'length', 'depth', 'height')

def item(kind, x=0., y=0.):
    return dict(kind=kind, **dict(zip(FIELDS, (x, y, 0., *KINDS[kind][1]))))

def validate(layout, check_spawn=True):
    if not isinstance(layout, dict) or type(layout.get('version')) is not int or layout['version'] != 1:
        raise ValueError('バージョン1の部屋ファイルを選択してください。')
    items = layout.get('items')
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError('配置できる家具は100個までです。')
    for i, obj in enumerate(items, 1):
        if not isinstance(obj, dict) or not isinstance(obj.get('kind'), str) or obj['kind'] not in KINDS:
            raise ValueError(f'{i}番の家具種別が不明です。')
        for key in FIELDS:
            v = obj.get(key)
            if type(v) not in (int, float) or not -1000 <= v <= 1000:
                raise ValueError(f'{i}番の {key} に有限の数値を入力してください。')
        x, y, yaw, length, depth, height = (obj[k] for k in FIELDS)
        if max(abs(x), abs(y)) > 30 or not all(.05 <= n <= 20 for n in (length, depth, height)):
            raise ValueError('中心座標は±30 m、寸法は0.05〜20 mで指定してください。')
        validate_objects(obj)
        # Closest point of the rotated footprint to the spawn safety circle.
        a = math.radians(yaw)
        dx = max(0, abs(x*math.cos(a)+y*math.sin(a))-length/2)
        dy = max(0, abs(-x*math.sin(a)+y*math.cos(a))-depth/2)
        if check_spawn and math.hypot(dx, dy) < .45:
            raise ValueError(f'{i}番の家具がロボットの初期位置（半径0.45 m）と重なります。')
    if sum(len(obj.get('objects', [])) for obj in items) > 100:
        raise ValueError('部屋全体に配置できる机上物体は100個までです。')
    return layout

def read(path):
    if path.stat().st_size > 256*1024:
        raise ValueError('部屋ファイルが大きすぎます。')
    return validate(json.loads(path.read_text(encoding='utf-8')))

def write(path, layout):
    data = json.dumps(validate(layout), ensure_ascii=False, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode='w', encoding='utf-8') as f:
        temp = Path(f.name)
        try:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)

def parts(obj):
    """Yield local centers and full box sizes; tables and chairs have open leg space."""
    length, depth, height = (obj[k] for k in FIELDS[3:])
    if obj['kind'] in ('wall', 'cabinet'):
        yield (0, 0, height/2), (length, depth, height)
        return
    chair = obj['kind'] == 'chair'
    surface = height*.52 if chair else height
    thick = min(.045, surface*.18)
    leg = min(.065, length*.15, depth*.15)
    yield (0, 0, surface-thick/2), (length, depth, thick)
    for sx in (-1, 1):
        for sy in (-1, 1):
            yield (sx*(length/2-leg), sy*(depth/2-leg), (surface-thick)/2), (leg, leg, surface-thick)
    if chair:
        yield (-length/2+leg/2, 0, (height+surface)/2), (leg, depth, height-surface)

def descriptions(layout):
    result = {}
    for i, obj in enumerate(layout['items']):
        a = math.radians(obj['yaw'])/2
        rgba = KINDS[obj['kind']][2]
        geoms = [dict(type='box', pos=list(p), size=[n/2 for n in s], rgba=list(rgba)) for p,s in parts(obj)]
        result[f'happy_room_{i:03d}'] = (dict(geoms=geoms), [obj['x'],obj['y'],0.,math.cos(a),0.,0.,math.sin(a)])
        for j, prop in enumerate(obj.get('objects', [])):
            asset = PROPS[prop['kind']]
            x,y = world_xy(obj, prop['x'], prop['y'])
            angle = math.radians(obj['yaw'] + prop['yaw'])/2
            pose = [x, y, obj['height']+asset['half_height'], math.cos(angle), 0., 0., math.sin(angle)]
            result[f'happy_room_{i:03d}_prop_{j:03d}'] = (asset, pose)
    return result

def compose(scene, layout, folder):
    """Create a stack-private scene; the installed arm models stay reusable."""
    scene = Path(scene)
    tree = ET.parse(scene)
    for element in tree.iter():
        ref = element.get('file')
        if ref and not Path(ref).is_absolute():
            element.set('file', str(scene.parent/ref))
    world = tree.find('worldbody')
    def vec(values):
        return ' '.join(map(str, values))
    for name, (description, pose) in descriptions(layout).items():
        body = ET.SubElement(world, 'body', name=name, pos=vec(pose[:3]), quat=vec(pose[3:]))
        if 'mass' in description:
            ET.SubElement(body, 'freejoint', name=name+'_free')
        for i,g in enumerate(description['geoms']):
            geom = ET.SubElement(body, 'geom', name=f'{name}_{i}', type=g['type'], pos=vec(g['pos']),
                          size=vec(g['size']), rgba=vec(g['rgba']), group='1', contype='1', conaffinity='7')
            if 'mass' in description:
                # Split the mass across components using their geometric volumes.
                geom.set('condim','4')
                geom.set('friction','1 0.01 0.001')
        if 'mass' in description:
            geoms = body.findall('geom')
            volumes = []
            for part in description['geoms']:
                size = part['size']
                if part['type'] == 'cylinder':
                    volumes.append(2*math.pi*size[0]**2*size[1])
                elif part['type'] == 'ellipsoid':
                    volumes.append(4*math.pi*math.prod(size)/3)
                else:
                    volumes.append(8*math.prod(size))
            for geom, volume in zip(geoms, volumes):
                geom.set('mass', str(description['mass']*volume/sum(volumes)))
    out = Path(folder)/'scene.xml'
    tree.write(out, encoding='utf-8')
    return out
