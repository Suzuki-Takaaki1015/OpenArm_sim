"""Replay Livox MID-360 reference directions, FOV-adapted for MID-360S.

This is not a calibrated MID-360S optical/mechanical model. See SCAN_SOURCE.json.
The 800000-row vendor reference repeats after 4 simulated seconds at 200k rays/s.
"""
from functools import lru_cache
from pathlib import Path
import math
import numpy as np

SAMPLE_RATE = 200000
REFERENCE_SIZE = 800000
SOURCE_ELEVATION = (-7.2123, 52.164)
PATTERN_NAME = 'livox_mid360_reference_fov_adapted'

@lru_cache(maxsize=1)
def reference_angles():
    with np.load(Path(__file__).with_name('lidar_assets')/'mid360_scan.npz',allow_pickle=False) as asset:
        angles=asset['angles_deg'].astype(np.float64)
    if angles.shape!=(REFERENCE_SIZE,2) or not np.isfinite(angles).all():
        raise ValueError('Invalid bundled Livox scan reference')
    angles.setflags(write=False)
    return angles

def sample_directions(count,start_index=0,span=40000,low=-7.,high=52.):
    """Preserve time-ordered source samples; reduced density spans the SAME window.

Stratified selection prevents regular thinning from always selecting the same
member of the source's interleaved beams. It never fabricates a new angle.
"""
    if (type(count) is not int or type(span) is not int or not 1<=count<=span
            or not -90<low<high<90 or not isinstance(start_index,(int,np.integer))):
        raise ValueError('Invalid scan window')
    if count==span:
        offsets=np.arange(span,dtype=np.int64)
    else:
        # Stateless integer hash for reproducible selection within disjoint bins.
        h=(np.arange(count,dtype=np.uint64)+np.uint64(start_index % (2**32))) & np.uint64(0xffffffff)
        h=((h^(h>>16))*np.uint64(0x7feb352d)) & np.uint64(0xffffffff)
        h=((h^(h>>15))*np.uint64(0x846ca68b)) & np.uint64(0xffffffff)
        h=h^(h>>16)
        begin=np.arange(count,dtype=np.int64)*span//count
        end=(np.arange(count,dtype=np.int64)+1)*span//count
        offsets=begin+(h % (end-begin).astype(np.uint64)).astype(np.int64)
    angles=reference_angles()[(start_index+offsets)%REFERENCE_SIZE]
    az=np.radians(angles[:,0])
    elevation=90.-angles[:,1]
    el=np.radians(low+(elevation-SOURCE_ELEVATION[0])*(high-low)/(SOURCE_ELEVATION[1]-SOURCE_ELEVATION[0]))
    # Roundoff only; do not pile out-of-FOV source directions onto the edges.
    el=np.clip(el,math.radians(low),math.radians(high))
    return np.column_stack((np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)))

def directions(count,frame,low=-7.,high=52.):
    """Compatibility helper: frame indexes fixed 0.2-s source windows."""
    return sample_directions(count,int(frame)*40000,40000,low,high)

def window_start(end_time,window_seconds):
    if not math.isfinite(end_time) or not math.isfinite(window_seconds) or end_time<0 or window_seconds<=0:
        raise ValueError('Invalid simulation time/window')
    return round(end_time*SAMPLE_RATE)-round(window_seconds*SAMPLE_RATE)

def scan(mj,m,d,origin,rotation,rays,exclude,minimum,maximum):
    world=np.ascontiguousarray(rays@rotation.T,dtype=np.float64)
    ids=np.full(len(rays),-1,dtype=np.int32);dist=np.full(len(rays),-1.,dtype=np.float64)
    groups=np.array([1,1,1,0,0,0],dtype=np.uint8)
    mj.mj_multiRay(m,d,np.asarray(origin,dtype=np.float64),world.ravel(),groups,1,exclude,ids,dist,None,len(rays),maximum)
    valid=(dist>=minimum)&(dist<=maximum)&np.isfinite(dist)
    return (rays[valid]*dist[valid,None]).astype('<f4'),ids[valid]
