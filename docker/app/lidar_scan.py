"""Ideal time-varying angular sampling, NOT Livox's proprietary scan pattern."""
import math
import numpy as np
def directions(count,frame,low=-7.,high=52.):
    if count<1 or not -90<low<high<90:raise ValueError('Invalid scan configuration')
    i=np.arange(count,dtype=float)+frame*count+.5
    az=2*math.pi*np.mod(i*((math.sqrt(5)-1)/2),1)
    el=np.radians(low+(high-low)*np.mod(i*(math.sqrt(2)-1),1))
    return np.column_stack((np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)))
def scan(mj,m,d,origin,rotation,rays,exclude,minimum,maximum):
    world=np.ascontiguousarray(rays@rotation.T,dtype=np.float64)
    ids=np.full(len(rays),-1,dtype=np.int32);dist=np.full(len(rays),-1.,dtype=np.float64)
    groups=np.array([1,1,1,0,0,0],dtype=np.uint8)
    mj.mj_multiRay(m,d,np.asarray(origin,dtype=np.float64),world.ravel(),groups,1,exclude,ids,dist,None,len(rays),maximum)
    valid=(dist>=minimum)&(dist<=maximum)&np.isfinite(dist)
    return (rays[valid]*dist[valid,None]).astype('<f4'),ids[valid]
