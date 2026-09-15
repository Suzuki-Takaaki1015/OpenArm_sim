"""Physical spawn/despawn support; no attachment or grasp algorithm is implemented here."""
import random
import math
import mujoco
import numpy as np
from environment_assets import ITEMS

class DynamicObjects:
    def __init__(self, sim):
        self.sim=sim;self.active={key:False for key in ITEMS}
        self.bids={key:mujoco.mj_name2id(sim.model,mujoco.mjtObj.mjOBJ_BODY,obj['id']) for key,obj in ITEMS.items()}

    def set_enabled(self,key,enabled,reposition=False):
        m,d=self.sim.model,self.sim.data;obj=ITEMS[key];bid=self.bids[key]
        if bid<0:raise ValueError('Rebuild image: dynamic object is missing')
        joint=int(m.body_jntadr[bid]);q=int(m.jnt_qposadr[joint]);v=int(m.jnt_dofadr[joint])
        geoms=list(range(int(m.body_geomadr[bid]),int(m.body_geomadr[bid]+m.body_geomnum[bid])))
        if enabled and self.active[key] and not reposition:return
        if not enabled:
            d.qpos[q:q+7]=[list(ITEMS).index(key),0,-5,1,0,0,0];d.qvel[v:v+6]=0
            m.body_gravcomp[bid]=1;m.body_contype[bid]=m.body_conaffinity[bid]=0
            for g in geoms:m.geom_contype[g]=m.geom_conaffinity[g]=0;m.geom_rgba[g]=[0,0,0,0]
            self.active[key]=False;mujoco.mj_forward(m,d);return
        previous=(d.qpos[q:q+7].copy(),d.qvel[v:v+6].copy(),self.active[key])
        m.body_gravcomp[bid]=0;m.body_contype[bid]=m.body_conaffinity[bid]=1
        for g in geoms:m.geom_contype[g]=m.geom_conaffinity[g]=1
        for _ in range(50):
            x=random.uniform(.36,.64);y=random.uniform(-.25,.10);yaw=random.uniform(-math.pi,math.pi)
            # Keep the two objects apart, regardless of their current orientation.
            if any(other!=key and self.active[other] and np.linalg.norm(d.xpos[self.bids[other]][:2]-[x,y])<.14 for other in ITEMS):continue
            d.qpos[q:q+7]=[x,y,.16+obj['half_height']+.007,math.cos(yaw/2),0,0,math.sin(yaw/2)];d.qvel[v:v+6]=0
            mujoco.mj_forward(m,d)
            if any((int(c.geom1) in geoms or int(c.geom2) in geoms) and c.dist < 0 for c in d.contact):continue
            for g,desc in zip(geoms,obj['geoms']):m.geom_rgba[g]=desc['rgba']
            self.active[key]=True;return
        # Restore the previous object if a safe new location could not be found.
        if previous[2]:
            d.qpos[q:q+7]=previous[0];d.qvel[v:v+6]=previous[1];mujoco.mj_forward(m,d)
        else:self.set_enabled(key,False)
        raise ValueError('No collision-free placement found; move the arm away')

    def snapshot(self):
        d=self.sim.data
        return {key:{'enabled':self.active[key],'position':d.xpos[bid].tolist(),'quaternion_wxyz':d.xquat[bid].tolist()} for key,bid in self.bids.items()}
