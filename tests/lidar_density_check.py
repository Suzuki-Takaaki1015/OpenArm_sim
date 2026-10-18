"""Integration test for a disposable simulator: changes table/LiDAR settings."""
import json,time
from collections import deque
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2
from std_srvs.srv import SetBool,Trigger
from rcl_interfaces.srv import SetParametersAtomically
from rcl_interfaces.msg import Parameter,ParameterValue,ParameterType

def main():
    rclpy.init();node=Node('lidar_density_check');clouds=deque(maxlen=5)
    node.create_subscription(PointCloud2,'/lidar/points',lambda msg:clouds.append(msg),1)
    def call(kind,name,req):
        client=node.create_client(kind,name)
        try:
            assert client.wait_for_service(timeout_sec=90),name
            f=client.call_async(req);rclpy.spin_until_future_complete(node,f,timeout_sec=90)
            assert f.done() and f.result() is not None,name
            return f.result()
        finally:node.destroy_client(client)
    def enabled(name,value):
        q=SetBool.Request();q.data=value;assert call(SetBool,name,q).success
    def status():return json.loads(call(Trigger,'/openarm/lidar/status',Trigger.Request()).message)
    def params(count):
        q=SetParametersAtomically.Request();q.parameters=[Parameter(name='rays_per_frame',value=ParameterValue(type=ParameterType.PARAMETER_INTEGER,integer_value=count))]
        return call(SetParametersAtomically,'/openarm_mid360s_sim/set_parameters_atomically',q).result
    def wait_cloud():
        clouds.clear();end=time.monotonic()+90
        while time.monotonic()<end:
            rclpy.spin_once(node,timeout_sec=.1)
            if clouds and clouds[-1].width:return clouds[-1].width
        raise AssertionError('No point cloud')
    try:
        initial=status()
        assert initial['rays_per_frame']==40000,'Default should be dense, not VM profile'
        assert initial['scan_pattern']=='livox_mid360_reference_fov_adapted'
        assert initial['reference_period_s']==4. and not initial['trajectory_calibrated']
        enabled('/openarm/set_obstacles',True)
        enabled('/openarm/lidar/set_enabled',True)
        wait_cloud();counts=[]
        for count in (800,8000,40000):
            assert params(count).successful
            # Discard old subscription data and allow changed density to take effect.
            end=time.monotonic()+2
            while time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.1)
            points=wait_cloud();s=status();assert s['enabled'] and not s['error'],s
            assert s['rays_per_frame']==count and 0<points<=count,s
            assert s['sample_start_index']==round(s['last_sim_time']*200000)-40000,s
            counts.append(points);print('DENSITY',count,points,s,flush=True)
        assert counts[2]>counts[0]*30 and counts[1]>counts[0]*5,counts
        for bad in (0,40001):
            assert not params(bad).successful
            assert status()['rays_per_frame']==40000
        enabled('/openarm/lidar/set_enabled',False)
        enabled('/openarm/lidar/set_enabled',True)
        assert wait_cloud()>counts[0]*30
        print('PASS: dense default, live profiles, invalid parameter rejection, restart',flush=True)
    finally:
        enabled('/openarm/lidar/set_enabled',False)
        node.destroy_node();rclpy.shutdown()
if __name__=='__main__':main()
