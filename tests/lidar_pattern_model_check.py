"""Static ray/occlusion acceptance on either generated OpenArm model.

Run with OPENARM_SCENE and OPENARM_YCB_ROOT configured (container entrypoint).
Uses disposable MuJoCo data, never commands ROS or changes a live simulation.
"""
import argparse,json,math,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'docker/app'))
if Path('/opt/openarm/app').exists():sys.path.insert(0,'/opt/openarm/app')
import mujoco,numpy as np
from environment_assets import ITEMS
from lidar_scan import sample_directions,scan

def previous_pattern(count,frame):
    i=np.arange(count)+frame*count+.5
    az=2*np.pi*np.mod(i*((math.sqrt(5)-1)/2),1)
    el=np.radians(-7+59*np.mod(i*(math.sqrt(2)-1),1))
    return np.c_[np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    spec=mujoco.MjSpec.from_file(os.environ['OPENARM_SCENE'])
    omitted={f'{o["id"]}_{i}' for o in ITEMS.values() for i in range(len(o['geoms']))}
    for geom in list(spec.geoms):
        if geom.name in omitted:spec.delete(geom)
    referenced={g.meshname for g in spec.geoms if g.meshname}
    for mesh in list(spec.meshes):
        if mesh.name not in referenced:spec.delete(mesh)
    for tex in spec.textures:
        tex.file='';tex.cubefiles=['']*6;tex.builtin=mujoco.mjtBuiltin.mjBUILTIN_FLAT;tex.width=4;tex.height=4
    xy=[(x,y) for x in (.30,.39,.48,.57,.66) for y in (-.25,-.125,0,.125,.25)]
    for mm in (10,20,40):
        side=mm/1000
        for i,(x,y) in enumerate(xy):
            b=spec.worldbody.add_body(name=f'probe_{mm}_{i}',pos=[x,y,.16+side/2])
            b.add_geom(name=f'probe_{mm}_{i}',type=mujoco.mjtGeom.mjGEOM_BOX,size=[side/2]*3,rgba=[1,1,0,1],group=5,contype=0,conaffinity=0)
    # Known occluder for an independent false-return regression, hidden initially.
    b=spec.worldbody.add_body(name='scan_test_occluder',pos=[.22,0,.27])
    b.add_geom(name='scan_test_occluder',type=mujoco.mjtGeom.mjGEOM_BOX,size=[.01,1.,.5],rgba=[.5,.5,.5,1],group=5,contype=0,conaffinity=0)
    m=spec.compile();d=mujoco.MjData(m);m.geom_group[m.geom_group==3]=5
    table=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_GEOM,'openarm_demo_table');m.geom_rgba[table]=[.5,.3,.2,1]
    mujoco.mj_forward(m,d)
    bid=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,'mid360s_link');exclude=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_BODY,'mid360s_mount')
    origin=d.xpos[bid].copy();R=d.xmat[bid].reshape(3,3).copy()
    def cast(rays):return scan(mujoco,m,d,origin,R,rays,exclude,.1,40)
    new=[sample_directions(40000,f*40000) for f in range(20)]
    old=[previous_pattern(40000,f) for f in range(20)]
    report={'model':os.environ.get('OPENARM_VERSION'),'rays_per_window':40000,'window_seconds':.2,'reference_windows':20,'cube_positions_xy_m':xy,'table':{},'small_cubes':{}}
    for name,frames in [('previous',old),('vendor_reference',new)]:
        bins=[]
        for rays in frames:
            p,ids=cast(rays);p=p[ids==table]@R.T+origin
            bins.append(np.histogram2d(p[:,0],p[:,1],bins=[50,70],range=[[.25,.75],[-.35,.35]])[0]>0)
        coverage=[float(b.mean()) for b in bins]
        integrated=[float(np.logical_or.reduce([bins[(f+k)%20] for k in range(5)]).mean()) for f in range(20)]
        report['table'][name]={'single_mean_1cm_coverage':float(np.mean(coverage)),'single_min_1cm_coverage':min(coverage),'one_second_mean_1cm_coverage':float(np.mean(integrated)),'one_second_min_1cm_coverage':min(integrated)}
        print('TABLE',name,report['table'][name],flush=True)
    assert report['table']['vendor_reference']['single_mean_1cm_coverage']>report['table']['previous']['single_mean_1cm_coverage']+.10
    assert report['table']['vendor_reference']['one_second_min_1cm_coverage']>.90
    for mm in (10,20,40):
        gids=np.array([mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_GEOM,f'probe_{mm}_{i}') for i in range(25)])
        m.geom_group[gids]=2
        targets=np.array([[x,y,.16+mm/1000] for x,y in xy]);v=targets-origin;length=np.linalg.norm(v,axis=1);rays=(v/length[:,None])@R
        _,center_ids=cast(rays)
        # Test layout must have a clear, in-FOV top-center line of sight to EVERY cube.
        assert np.array_equal(center_ids,gids),(mm,center_ids,gids)
        result={}
        for name,frames in [('previous',old),('vendor_reference',new)]:
            counts=[]
            for rays in frames:
                _,ids=cast(rays);hist=np.bincount(ids,minlength=m.ngeom);counts.append(hist[gids])
            counts=np.array(counts);sums=np.array([sum(counts[(f+k)%20] for k in range(5)) for f in range(20)])
            result[name]={'single_misses':int(np.count_nonzero(counts==0)),'single_trials':int(counts.size),'one_second_misses':int(np.count_nonzero(sums==0)),'one_second_trials':int(sums.size),'one_second_fewer_than_3_hits':int(np.count_nonzero(sums<3)),'single_min_hits':int(counts.min()),'one_second_min_hits':int(sums.min()),'one_second_mean_hits':float(sums.mean())}
        report['small_cubes'][str(mm)]=result
        print('CUBES mm',mm,result,flush=True)
        assert result['vendor_reference']['one_second_misses']<=result['previous']['one_second_misses']
        if mm>=20:assert result['vendor_reference']['one_second_misses']==0
        m.geom_group[gids]=5
    # With a wall between sensor and all targets, NO hidden cube may be returned.
    m.geom_group[gids]=2
    blocker=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_GEOM,'scan_test_occluder');m.geom_group[blocker]=2
    _,ids=cast(new[0]);assert not np.isin(ids,gids).any(),'Returns behind opaque wall'
    report['occlusion_check']='pass'
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print('PASS scan coverage, small-object sampling, opaque occlusion',flush=True)
if __name__=='__main__':main()
