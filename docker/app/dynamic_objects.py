"""Optional rigid objects and anchored furniture, with validated support placement."""
import random
import math
import mujoco
import numpy as np
from environment_assets import ITEMS
from scene_objects import OBJECTS
from ycb_assets import set_visibility

def rot(yaw):
    c,s=math.cos(yaw),math.sin(yaw)
    return np.array([[c,-s],[s,c]])

def overlapping(a,b):
    """Strict 3-D overlap of upright oriented boxes, allowing touching faces."""
    pa,ha,ya=a;pb,hb,yb=b
    if abs(pa[2]-pb[2]) >= ha[2]+hb[2]-.0005:return False
    ra,rb=rot(ya),rot(yb);delta=np.array(pb[:2])-pa[:2]
    for axis in (ra[:,0],ra[:,1],rb[:,0],rb[:,1]):
        if abs(delta@axis) >= abs(ra.T@axis)@ha[:2]+abs(rb.T@axis)@hb[:2]-.0005:return False
    return True

class DynamicObjects:
    def __init__(self,sim):
        self.sim=sim
        self.active={key:False for key in ITEMS}
        self.supports={key:None for key in ITEMS}
        self.bids={key:mujoco.mj_name2id(sim.model,mujoco.mjtObj.mjOBJ_BODY,obj['id']) for key,obj in ITEMS.items()}

    def geoms(self,key):
        m=self.sim.model;b=self.bids[key]
        return list(range(int(m.body_geomadr[b]),int(m.body_geomadr[b]+m.body_geomnum[b])))

    def pose(self,key):
        m,d=self.sim.model,self.sim.data;b=self.bids[key]
        if ITEMS[key].get('furniture'):
            i=m.body_mocapid[b]
            return np.r_[d.mocap_pos[i],d.mocap_quat[i]].copy()
        q=m.jnt_qposadr[m.body_jntadr[b]]
        return d.qpos[q:q+7].copy()

    def write_pose(self,key,pose):
        m,d=self.sim.model,self.sim.data;b=self.bids[key]
        if ITEMS[key].get('furniture'):
            i=m.body_mocapid[b];d.mocap_pos[i]=pose[:3];d.mocap_quat[i]=pose[3:]
        else:
            j=m.body_jntadr[b];q=m.jnt_qposadr[j];v=m.jnt_dofadr[j]
            d.qpos[q:q+7]=pose;d.qvel[v:v+6]=0

    def masks(self,key,enabled):
        m=self.sim.model;b=self.bids[key]
        m.body_contype[b]=m.body_conaffinity[b]=int(enabled)
        if not ITEMS[key].get('furniture'):m.body_gravcomp[b]=0 if enabled else 1
        for g,desc in zip(self.geoms(key),ITEMS[key]['geoms']):
            m.geom_contype[g]=m.geom_conaffinity[g]=int(enabled and desc.get('collision',True))
            set_visibility(m,g,desc,enabled)

    def table_active(self):
        m=self.sim.model
        g=mujoco.mj_name2id(m,mujoco.mjtObj.mjOBJ_GEOM,OBJECTS[0]['id'])
        return g>=0 and bool(m.geom_contype[g])

    def surface(self,name):
        if name=='worktable':
            if not self.table_active():raise ValueError('Enable the worktable first')
            t=OBJECTS[0]
            return np.array(t['position'][:2]),np.array(t['size'][:2]),t['position'][2]+t['size'][2]/2,0.
        try:
            key,which=name.split(':')
            obj=ITEMS[key]
            s=next(s for s in obj['surfaces'] if s['name']==which)
        except (ValueError,KeyError,StopIteration):raise ValueError('Unknown support surface')
        if not self.active[key]:raise ValueError('Place the supporting furniture first')
        p=self.pose(key);yaw=2*math.atan2(p[6],p[3])
        centre=p[:2]+rot(yaw)@np.array(s['position'][:2])
        return centre,np.array(s['size']),p[2]+s['position'][2],yaw

    def occupied(self,key):
        # Associations are conservative even after an object falls or is grasped.
        if any(self.active[k] and (self.supports[k] or '').startswith(key+':') for k in ITEMS):return True
        # Also protect objects put here by physics/member code, without an association.
        p=self.pose(key);half=np.array(ITEMS[key]['size'])/2
        yaw=2*math.atan2(p[6],p[3])
        for k in ITEMS:
            if not self.active[k] or ITEMS[k].get('furniture'):continue
            op=self.pose(k);h=self.half(k)
            xy=rot(yaw).T@(op[:2]-p[:2])
            if np.all(np.abs(xy)<half[:2]+max(h[:2])) and abs(op[2]-p[2])<half[2]+h[2]+.025:return True
        return False

    def half(self,key):
        obj=ITEMS[key]
        if 'size' in obj:return np.array(obj['size'])/2
        return np.max([np.abs(g['pos'])+np.array(g['size'] if g['type']=='box' else [g['size'][0],g['size'][0],g['size'][-1]]) for g in obj['geoms']],axis=0)

    def furniture_boxes(self,key):
        p=self.pose(key);yaw=2*math.atan2(p[6],p[3]);r=rot(yaw)
        for g in ITEMS[key]['geoms']:
            centre=p[:3].copy();centre[:2]+=r@np.array(g['pos'][:2]);centre[2]+=g['pos'][2]
            yield centre,np.array(g['size']),yaw

    def collision(self,key):
        m,d=self.sim.model,self.sim.data
        gs=set(self.geoms(key))
        if any((int(c.geom1) in gs or int(c.geom2) in gs) and c.dist < -.0001 for c in d.contact):return True
        if not ITEMS[key].get('furniture'):return False
        # MuJoCo excludes mocap-vs-static pairs, including the fixed robot base.
        # Use the collision shapes themselves; visual-only meshes are excluded.
        for g in gs:
            for h in range(m.ngeom):
                if h in gs or not m.geom_contype[h]:continue
                body=int(m.geom_bodyid[h])
                if m.body_weldid[body]!=0 and m.body_mocapid[body]<0:continue
                if mujoco.mj_geomDistance(m,d,g,h,.001,None)<-.0001:return True
        # Also use upright box SAT for compound furniture and the worktable.
        others=[]
        if self.table_active():
            others += [(np.array(o['position']),np.array(o['size'])/2,0.) for o in OBJECTS]
        for k in ITEMS:
            if k!=key and self.active[k] and ITEMS[k].get('furniture'):
                others.extend(self.furniture_boxes(k))
        return any(overlapping(a,b) for a in self.furniture_boxes(key) for b in others)

    def set_enabled(self,key,enabled,reposition=False,pose=None,support='worktable'):
        m,d=self.sim.model,self.sim.data;obj=ITEMS[key]
        if self.bids[key]<0:raise ValueError('Rebuild image: asset missing')
        furniture=obj.get('furniture',False)
        if enabled and self.active[key] and not reposition:return
        if furniture and self.active[key] and self.occupied(key):
            raise ValueError('Remove objects on/inside this furniture before moving or hiding it')
        if not enabled:
            self.write_pose(key,[list(ITEMS).index(key),0,-5,1,0,0,0])
            self.masks(key,False);self.active[key]=False;self.supports[key]=None
            mujoco.mj_forward(m,d);return
        if pose is not None and (len(pose)!=3 or not all(math.isfinite(v) for v in pose)):
            raise ValueError('X, Y and yaw must be finite numbers')
        if pose is not None and (max(abs(pose[0]),abs(pose[1]))>5 or abs(pose[2])>2*math.pi):
            raise ValueError('Placement range: X/Y +/-5 m, yaw +/-360 degrees')
        if furniture and pose is None:
            raise ValueError('Furniture requires an explicit floor position')
        half=self.half(key)
        if not furniture:
            centre,size,height,syaw=self.surface(support)
            def bounds(yaw):
                r=np.abs(rot(yaw-syaw));room=size/2-r@half[:2]-.002
                return room
            if pose is not None:
                xy=rot(syaw).T@(np.array(pose[:2])-centre)
                if np.any(np.abs(xy)>bounds(pose[2])):
                    raise ValueError('Object footprint extends beyond the selected support surface')
        old=self.pose(key);old_active=self.active[key];old_support=self.supports[key]
        velocity=None
        if not furniture:
            v=m.jnt_dofadr[m.body_jntadr[self.bids[key]]];velocity=d.qvel[v:v+6].copy()
        self.masks(key,True)
        for _ in range(1 if pose is not None else 50):
            if pose is None:
                yaw=random.uniform(-math.pi,math.pi);room=bounds(yaw)
                if np.any(room<0):continue
                x,y=centre+rot(syaw)@np.array([random.uniform(-v,v) for v in room])
            else:x,y,yaw=pose
            z=obj['half_height'] if furniture else height+obj['half_height']+.007
            self.write_pose(key,[x,y,z,math.cos(yaw/2),0,0,math.sin(yaw/2)])
            mujoco.mj_forward(m,d)
            if self.collision(key):continue
            self.active[key]=True;self.supports[key]=None if furniture else support
            return
        self.write_pose(key,old);self.masks(key,old_active)
        if velocity is not None:d.qvel[v:v+6]=velocity
        self.active[key]=old_active;self.supports[key]=old_support;mujoco.mj_forward(m,d)
        raise ValueError('No collision-free placement; previous state preserved')

    def snapshot(self):
        d=self.sim.data
        return {k:dict(enabled=self.active[k],position=d.xpos[b].tolist(),
                       quaternion_wxyz=d.xquat[b].tolist(),support=self.supports[k])
                for k,b in self.bids.items()}
