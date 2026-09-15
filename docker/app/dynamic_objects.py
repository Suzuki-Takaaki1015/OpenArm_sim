"""Physical spawn/despawn support; no attachment or grasp algorithm is implemented here."""
import random
import math
import mujoco
import numpy as np
from environment_assets import ITEMS
from scene_objects import OBJECTS
from ycb_assets import set_visibility
class DynamicObjects:
    def __init__(self, sim):
        self.sim=sim;self.active={key:False for key in ITEMS}
        self.bids={key:mujoco.mj_name2id(sim.model,mujoco.mjtObj.mjOBJ_BODY,obj['id']) for key,obj in ITEMS.items()}
    def set_enabled(self,key,enabled,reposition=False,pose=None):
        m,d=self.sim.model,self.sim.data;obj=ITEMS[key];bid=self.bids[key]
        if bid<0:raise ValueError('Rebuild image: dynamic object is missing')
        joint=int(m.body_jntadr[bid]);q=int(m.jnt_qposadr[joint]);v=int(m.jnt_dofadr[joint])
        geoms=list(range(int(m.body_geomadr[bid]),int(m.body_geomadr[bid]+m.body_geomnum[bid])))
        if enabled and self.active[key] and not reposition:return
        if not enabled:
            d.qpos[q:q+7]=[list(ITEMS).index(key),0,-5,1,0,0,0];d.qvel[v:v+6]=0
            m.body_gravcomp[bid]=1;m.body_contype[bid]=m.body_conaffinity[bid]=0
            for g,desc in zip(geoms,obj['geoms']):
                m.geom_contype[g]=m.geom_conaffinity[g]=0;set_visibility(m,g,desc,False)
            self.active[key]=False;mujoco.mj_forward(m,d);return
        table=OBJECTS[0]
        if 'size' in obj:half=np.array(obj['size'][:2])/2
        else:
            half=np.max([np.abs(g['pos'][:2])+np.array(g['size'][:2] if g['type']=='box' else [g['size'][0]]*2) for g in obj['geoms']],axis=0)
        def bounds(yaw):
            c,s=abs(math.cos(yaw)),abs(math.sin(yaw))
            footprint=np.array([c*half[0]+s*half[1],s*half[0]+c*half[1]])
            room=np.array(table['size'][:2])/2-footprint-.002
            centre=np.array(table['position'][:2])
            return centre-room,centre+room
        if pose is not None:
            if len(pose)!=3 or not all(math.isfinite(t) for t in pose):raise ValueError('X, Y and yaw must be finite numbers')
            x,y,yaw=pose;lo,hi=bounds(yaw)
            if np.any(np.array([x,y])<lo) or np.any(np.array([x,y])>hi):
                raise ValueError('Object would extend beyond the worktable; choose a position closer to the centre or rotate it')
        previous=(d.qpos[q:q+7].copy(),d.qvel[v:v+6].copy(),self.active[key])
        m.body_gravcomp[bid]=0;m.body_contype[bid]=m.body_conaffinity[bid]=1
        for g,desc in zip(geoms,obj['geoms']):m.geom_contype[g]=m.geom_conaffinity[g]=int(desc.get('collision',True))
        for _ in range(1 if pose is not None else 50):
            if pose is None:
                yaw=random.uniform(-math.pi,math.pi);lo,hi=bounds(yaw)
                if np.any(hi<lo):continue
                x,y=[random.uniform(float(a),float(b)) for a,b in zip(lo,hi)]
            else:x,y,yaw=pose
            height=table['position'][2]+table['size'][2]/2+obj['half_height']+.007
            d.qpos[q:q+7]=[x,y,height,math.cos(yaw/2),0,0,math.sin(yaw/2)];d.qvel[v:v+6]=0
            mujoco.mj_forward(m,d)
            if any((int(c.geom1) in geoms or int(c.geom2) in geoms) and c.dist < 0 for c in d.contact):continue
            for g,desc in zip(geoms,obj['geoms']):set_visibility(m,g,desc,True)
            self.active[key]=True;return
        # Restore the previous object if a safe new location could not be found.
        if previous[2]:
            d.qpos[q:q+7]=previous[0];d.qvel[v:v+6]=previous[1];mujoco.mj_forward(m,d)
        else:self.set_enabled(key,False)
        raise ValueError('Placement intersects the robot or another object; previous position preserved' if pose is not None else 'No collision-free placement found; move the arm away')
    def snapshot(self):
        d=self.sim.data
        return {key:{'enabled':self.active[key],'position':d.xpos[bid].tolist(),'quaternion_wxyz':d.xquat[bid].tolist()} for key,bid in self.bids.items()}
