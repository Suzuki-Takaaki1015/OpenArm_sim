"""Material, physical-invariance and camera checks for the generated models."""
import os,json,hashlib
from pathlib import Path
import xml.etree.ElementTree as E
import numpy as np,mujoco as mj
mode=os.environ.get('CHECK_MODE','after')
report={}
for version,name in [(1,'openarm_bimanual.xml'),(2,'simulation_robot.xml')]:
    path=Path(f'/opt/openarm/models/v{version}/{name}')
    m=mj.MjModel.from_xml_path(str(path));data=mj.MjData(m);mj.mj_forward(m,data)
    physics={}
    for field in ('body_mass','body_inertia','body_ipos','body_iquat','body_pos','body_quat','jnt_pos','jnt_axis','jnt_range','dof_damping'):
        physics[field]=getattr(m,field).tolist()
    collisions={}
    for i in range(m.ngeom):
        if not (m.geom_contype[i] or m.geom_conaffinity[i]):continue
        key=mj.mj_id2name(m,mj.mjtObj.mjOBJ_GEOM,i)
        collisions[key]=dict(body=int(m.geom_bodyid[i]),type=int(m.geom_type[i]),
            pos=m.geom_pos[i].tolist(),quat=m.geom_quat[i].tolist(),size=m.geom_size[i].tolist(),
            contype=int(m.geom_contype[i]),conaffinity=int(m.geom_conaffinity[i]))
    report[str(version)]=dict(physics=physics,collisions=collisions)
    if mode=='after':
        if version==2:
            folder=path.parent
            def triangles(name):
                raw=(folder/name).read_bytes()
                return [raw[i+12:i+50] for i in range(84,len(raw),50)]
            assert sorted(triangles('camera_exposed_support_reference.stl'))==sorted(
                triangles('camera_exposed_pedestal.stl')+triangles('camera_exposed_column.stl'))
            dtype=np.dtype([('n','<f4',(3,)),('v','<f4',(3,3)),('a','<u2')])
            for filename in ('camera_exposed_pedestal.stl','camera_exposed_column.stl'):
                facets=np.frombuffer((folder/filename).read_bytes(),dtype=dtype,offset=84)
                vertices=facets['v'].astype(float)
                cross=np.cross(vertices[:,1]-vertices[:,0],vertices[:,2]-vertices[:,0])
                length=np.linalg.norm(cross,axis=1);valid=length>1e-12
                assert np.allclose(facets['n'][valid],cross[valid]/length[valid,None],atol=1e-5)

        urdf=E.parse(f'/opt/openarm/config/v{version}/openarm.urdf')
        links=urdf.findall("link")
        support=[l for l in links if l.get('name','').startswith('openarm_body_link0_display_')]
        assert support and all(len(l.findall('visual'))==1 and not l.findall('collision') for l in support)
        colors=[np.fromstring(l.find('visual/material/color').get('rgba'),sep=' ') for l in support]
        assert any(np.allclose(c,[.796,.796,.796,1],atol=.001) for c in colors)
        assert any(np.allclose(c,[.65,.65,.68,1]) for c in colors)
        assert any(np.allclose(c,[.15,.15,.17,1]) for c in colors)
        assert len({v.get('name') for v in urdf.findall('.//visual/material')})==len(urdf.findall('.//visual/material'))
        # Compare URDF geometry origins to compiled MuJoCo mesh frames.
        # Undo MuJoCo's mesh recentering; RViz loads the original mesh vertices.
        def rotation(q):
            out=np.zeros(9);mj.mju_quat2Mat(out,np.asarray(q,dtype=float));return out.reshape(3,3)
        def from_rpy(values):
            r,p,y=values;cr,sr=np.cos(r),np.sin(r);cp,sp=np.cos(p),np.sin(p);cy,sy=np.cos(y),np.sin(y)
            return np.array([[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],
                             [sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]])
        checked=0
        for body in E.parse(path).getroot().iter('body'):
            name=body.get('name');bid=mj.mj_name2id(m,mj.mjtObj.mjOBJ_BODY,name)
            offsets={'visual':0,'collision':0}
            for offset,geom in enumerate(body.findall('geom')):
                gid=int(m.body_geomadr[bid])+offset
                purpose='collision' if geom.get('class') in ('collision','fingertip','pedestal_collision') else 'visual'
                linkname=f'{name}_display_{gid}' if name=='openarm_body_link0' and purpose=='visual' else name
                link=urdf.find(f"link[@name='{linkname}']")
                index=0 if linkname!=name else offsets[purpose]
                element=link.findall(purpose)[index];offsets[purpose]+=1
                frame=element.find('origin')
                actual=from_rpy(np.fromstring(frame.get('rpy'),sep=' '))
                meshid=int(m.geom_dataid[gid])
                expected=rotation(m.geom_quat[gid])@rotation(m.mesh_quat[meshid]).T
                expected_pos=m.geom_pos[gid]-expected@m.mesh_pos[meshid]
                assert np.allclose(actual,expected,atol=1e-8),(version,name,geom.get('mesh'),'rotation')
                assert np.allclose(np.fromstring(frame.get('xyz'),sep=' '),expected_pos,atol=1e-8),(version,name,'position')
                checked+=1
        print('PASS URDF/MuJoCo geometry frames',version,checked,flush=True)
        # Optical ray segmentation must not see the robot's supporting column.
        scene=mj.MjModel.from_xml_path(f'/opt/openarm/models/v{version}/simulation_scene.xml')
        d=mj.MjData(scene);mj.mj_forward(scene,d)
        r=mj.Renderer(scene,180,320);r.enable_segmentation_rendering();r.update_scene(d,camera='d435_color')
        image=r.render();ids=np.unique(image[:,:,0])
        visible=[mj.mj_id2name(scene,mj.mjtObj.mjOBJ_GEOM,int(i)) for i in ids if i>=0]
        assert all(n=='floor' for n in visible),visible
        r.disable_segmentation_rendering();r.enable_depth_rendering();r.update_scene(d,camera='d435_depth')
        assert np.isfinite(r.render()).all();r.close()
        print('PASS materials, visual-only links, clear RGB and finite depth',version,flush=True)
out=Path('/tmp/render-model-'+mode+'.json');out.write_text(json.dumps(report))
if mode=='after' and Path('/tmp/render-model-before.json').exists():
    before=json.loads(Path('/tmp/render-model-before.json').read_text())
    for version in report:
        for field,values in before[version]['physics'].items():
            assert np.allclose(values,report[version]['physics'][field],atol=1e-12,rtol=1e-10),('physics changed',version,field)
        for name,geom in before[version]['collisions'].items():
            for field,values in geom.items():
                assert np.allclose(values,report[version]['collisions'][name][field],atol=1e-12,rtol=1e-10),(version,name,field)
    print('PASS both models: unchanged masses/inertia/joints/contact geometry',flush=True)
