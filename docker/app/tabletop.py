"""Tabletop assets and placement geometry. Lengths in metres, angles in degrees."""
import math

# The two arm demos and the room editor share these rigid-body descriptions.
PROPS = {
    'box': dict(label='直方体', mass=.10, half_height=.04, geoms=[
        dict(type='box', size=[.025,.02,.04], pos=[0,0,0], rgba=[.95,.55,.12,1])]),
    'bottle': dict(label='500 mL PETボトル（近似）', mass=.525, half_height=.105, geoms=[
        dict(type='cylinder', size=[.0325,.085], pos=[0,0,-.02], rgba=[.3,.65,.85,1]),
        dict(type='ellipsoid', size=[.0325,.0325,.025], pos=[0,0,.065], rgba=[.3,.65,.85,1]),
        dict(type='cylinder', size=[.014,.014], pos=[0,0,.088], rgba=[.3,.65,.85,1]),
        dict(type='cylinder', size=[.015,.008], pos=[0,0,.102], rgba=[.1,.25,.65,1])]),
    'can': dict(label='飲料缶', mass=.36, half_height=.061, geoms=[
        dict(type='cylinder', size=[.033,.061], pos=[0,0,0], rgba=[.67,.24,.19,1])]),
}


def rotate(x, y, degrees):
    a = math.radians(degrees)
    return x*math.cos(a)-y*math.sin(a), x*math.sin(a)+y*math.cos(a)


def world_xy(table, x, y):
    dx, dy = rotate(x, y, table['yaw'])
    return table['x'] + dx, table['y'] + dy


def footprint(obj):
    base = PROPS[obj['kind']]['geoms'][0]
    return tuple(base['size'][:2]) if base['type'] == 'box' else (base['size'][0],)*2


def extent(obj, axis):
    hx, hy = footprint(obj)
    if obj['kind'] != 'box':
        return hx
    x, y = rotate(1., 0., obj['yaw']-axis)
    return abs(x)*hx + abs(y)*hy


def overlaps(a, b):
    dx, dy = b['x']-a['x'], b['y']-a['y']
    if a['kind'] == b['kind'] == 'box':
        for axis in (a['yaw'], a['yaw']+90, b['yaw'], b['yaw']+90):
            separation, _ = rotate(dx, dy, -axis)
            if abs(separation) >= extent(a, axis)+extent(b, axis)-1e-8:
                return False
        return True
    if a['kind'] != 'box' and b['kind'] != 'box':
        return math.hypot(dx,dy) < footprint(a)[0]+footprint(b)[0]-1e-8
    box, circle = (a,b) if a['kind'] == 'box' else (b,a)
    x, y = rotate(circle['x']-box['x'], circle['y']-box['y'], -box['yaw'])
    hx, hy = footprint(box)
    return math.hypot(max(0.,abs(x)-hx), max(0.,abs(y)-hy)) < footprint(circle)[0]-1e-8


def validate_objects(table):
    objects = table.get('objects', [])
    if not isinstance(objects,list) or len(objects)>100:
        raise ValueError('机上の物体は100個までです。')
    if objects and table['kind'] != 'table':
        raise ValueError('物体を配置できるのは机の天板です。')
    for i, obj in enumerate(objects):
        if not isinstance(obj,dict) or not isinstance(obj.get('kind'),str) or obj['kind'] not in PROPS:
            raise ValueError('不明な机上物体です。')
        for key in ('x','y','yaw'):
            v = obj.get(key)
            if type(v) not in (int,float) or not -1000 <= v <= 1000:
                raise ValueError('位置と向きに有限の数値を入力してください。')
        if (abs(obj['x'])+extent(obj,0) > table['length']/2+1e-8 or
                abs(obj['y'])+extent(obj,90) > table['depth']/2+1e-8):
            raise ValueError('物体全体が天板の内側に収まる位置を選んでください。')
        if any(overlaps(obj, other) for other in objects[:i]):
            raise ValueError('机上の物体が重なっています。位置を離してください。')
