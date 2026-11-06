"""Run in the built mode-3 image. Check both LiDAR variants of the mobile chest."""
import math
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco as mj
import numpy as np

from camera_mount import config
from mobile_camera_datum import mobile_d435


def mesh_bounds(model, data, name):
    mesh = model.mesh(name)
    geom = np.flatnonzero((model.geom_type == mj.mjtGeom.mjGEOM_MESH) & (model.geom_dataid == mesh.id))[0]
    start, size = model.mesh_vertadr[mesh.id], model.mesh_vertnum[mesh.id]
    vertices = model.mesh_vert[start:start+size] @ data.geom_xmat[geom].reshape(3, 3).T + data.geom_xpos[geom]
    return vertices.min(axis=0), vertices.max(axis=0)


def check(suffix):
    model = mj.MjModel.from_xml_path('/opt/openarm/models/mobile/simulation_scene'+suffix+'.xml')
    data = mj.MjData(model)
    mj.mj_forward(model, data)
    body = model.body('openarm_body_link0').id
    body_r = data.xmat[body].reshape(3, 3)
    camera = mobile_d435()
    shell_low, shell_high = mesh_bounds(model, data, 'hm_minion_mount')
    low, high = mesh_bounds(model, data, 'camera_mount_d435')
    # Camera sits between the cover's two lower cheeks, with a flush bottom edge.
    assert abs(low[2] - shell_low[2]) < .006, (low, shell_low)
    assert high[2] > shell_low[2]+.020 and abs((low[1]+high[1]-shell_low[1]-shell_high[1])/2) < .002
    root = ET.parse('/opt/openarm/config/mobile/openarm'+suffix+'.urdf')
    for kind, filename in [('visual', 'd435.obj'), ('collision', 'd435_collision.obj')]:
        items = [entry for entry in root.iter(kind) if entry.find('geometry/mesh') is not None and
                 Path(entry.find('geometry/mesh').get('filename')).name == filename]
        assert len(items) == 1, (kind, filename, len(items))
        origin = items[0].find('origin')
        np.testing.assert_allclose(np.fromstring(origin.get('xyz'), sep=' '), camera['front'])
        roll, pitch, yaw = np.fromstring(origin.get('rpy'), sep=' ')
        q = np.zeros(4)
        mj.mju_euler2Quat(q, np.array([roll,pitch,yaw]), 'XYZ')
        actual = np.zeros(9)
        mj.mju_quat2Mat(actual,q)
        np.testing.assert_allclose(actual.reshape(3,3), camera['mesh_rotation'], atol=1e-7)
    cfg = config()
    assert cfg['parent_frame'] == 'openarm_body_link0'
    for channel in ('color','depth'):
        sensor = model.camera('d435_'+channel).id
        assert model.cam_bodyid[sensor] == body
        offset = cfg['color_offset_m'] if channel == 'color' else np.zeros(3)
        expected = np.array(cfg['position_m']) + camera['rotation'] @ offset
        np.testing.assert_allclose(data.cam_xpos[sensor], data.xpos[body] + body_r @ expected, atol=1e-7)
        forward = -data.cam_xmat[sensor].reshape(3,3)[:,2]
        pitch = cfg['rpy_rad'][1]
        np.testing.assert_allclose(forward, body_r @ [math.cos(pitch),0,-math.sin(pitch)], atol=1e-7)
    print('PASS', suffix or 'with_lidar', 'camera bottom relative to cover bottom (mm)', round((low[2]-shell_low[2])*1000,2))
    return model, data


if __name__ == '__main__':
    os.environ['HAPPY_MOBILE']='1'
    for suffix in ('', '_no_lidar'):
        check(suffix)
