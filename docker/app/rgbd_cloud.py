"""Organized RGB point clouds projected from aligned optical-axis depth."""
from functools import lru_cache
import numpy as np
from sensor_msgs.msg import PointCloud2, PointField


@lru_cache(maxsize=8)
def projection(width,height,fx,fy,cx,cy):
    return ((np.arange(width,dtype=np.float32)-cx)/fx,
            (np.arange(height,dtype=np.float32)-cy)[:,None]/fy)


def point_cloud(info,rgb,depth_mm):
    msg=PointCloud2()
    msg.header=info.header
    msg.height,msg.width=depth_mm.shape
    msg.fields=[PointField(name=name,offset=i*4,datatype=PointField.FLOAT32,count=1)
                for i,name in enumerate(('x','y','z','rgb'))]
    msg.is_bigendian=False
    msg.is_dense=False
    msg.point_step=16
    msg.row_step=16*msg.width
    xs,ys=projection(msg.width,msg.height,info.k[0],info.k[4],info.k[2],info.k[5])
    z=depth_mm.astype(np.float32)*.001
    z[depth_mm==0]=np.nan
    points=np.empty((msg.height,msg.width,4),dtype='<f4')
    points[:,:,0]=xs*z
    points[:,:,1]=ys*z
    points[:,:,2]=z
    packed=points[:,:,3].view('<u4')
    packed[:]=(rgb[:,:,0].astype(np.uint32)<<16)|(rgb[:,:,1].astype(np.uint32)<<8)|rgb[:,:,2]
    msg.data=points.tobytes()
    return msg
