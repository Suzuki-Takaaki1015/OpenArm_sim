"""Create editable Jazzy configuration from the exact package versions installed."""
from pathlib import Path
import xml.etree.ElementTree as ET
import yaml
from mobile_speeds import NAV_LINEAR, NAV_YAW, LINEAR_ACCEL, YAW_ACCEL

dest=Path(__file__).parent
share=Path('/opt/ros/jazzy/share')
nav=yaml.safe_load((share/'nav2_bringup/params/nav2_params.yaml').read_text())
def params(name):
    return nav[name]['ros__parameters']

params('amcl').update(base_frame_id='base_link', robot_model_type='nav2_amcl::OmniMotionModel',
                      set_initial_pose=True,update_min_d=.08,update_min_a=.10)
ctrl=params('controller_server')
ctrl.update(min_y_velocity_threshold=.001,controller_frequency=15.)
ctrl['progress_checker'].update(required_movement_radius=.12)
ctrl['general_goal_checker'].update(xy_goal_tolerance=.12,yaw_goal_tolerance=.18)
# The UTM-30LX points along base_link +X. Track the route with this face leading.
ctrl['progress_checker'].update(plugin='nav2_controller::PoseProgressChecker', required_movement_angle=.25)
ctrl['FollowPath'] = {
    'plugin': 'nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController',
    'desired_linear_vel': NAV_LINEAR,
    'lookahead_dist': .45,
    'use_rotate_to_heading': True,
    'rotate_to_heading_min_angle': .30,
    'rotate_to_heading_angular_vel': NAV_YAW,
    # Seed enough rotation to overcome the omniwheel rollers at standstill.
    # The velocity smoother and bridge still apply the normal acceleration limit.
    'max_angular_accel': 4.0,
    'min_approach_linear_velocity': .11,
    'approach_velocity_scaling_dist': .55,
    'allow_reversing': False,
    'use_collision_detection': True,
}
# Keep replanning, obstacle checks, spinning and waiting in the stock recovery
# trees. A blind BackUp maneuver would defeat forward-only route following.
trees = share/'nav2_bt_navigator/behavior_trees'
for action, parameter in [('to_pose','default_nav_to_pose_bt_xml'),
                          ('through_poses','default_nav_through_poses_bt_xml')]:
    tree = ET.parse(trees/f'navigate_{action}_w_replanning_and_recovery.xml')
    for recovery in tree.iter('RoundRobin'):
        for backup in recovery.findall('BackUp'):
            recovery.remove(backup)
    if tree.find('.//BackUp') is not None:
        raise ValueError('Unexpected BackUp node in Nav2 recovery tree')
    output = dest/f'lidar_forward_{action}.xml'
    tree.write(output, encoding='utf-8')
    params('bt_navigator')[parameter] = str(output)

params('velocity_smoother').update(
    max_velocity=[NAV_LINEAR,0.,NAV_YAW],min_velocity=[0.,0.,-NAV_YAW],
    max_accel=[LINEAR_ACCEL,LINEAR_ACCEL,YAW_ACCEL],max_decel=[-LINEAR_ACCEL,-LINEAR_ACCEL,-YAW_ACCEL])
for name in ('controller_server','behavior_server','velocity_smoother','collision_monitor'):
    params(name)['enable_stamped_cmd_vel']=False
params('collision_monitor')['scan']['min_height']=-.1
params('collision_monitor')['base_frame_id']='base_link'
for name in ('local_costmap','global_costmap'):
    cm=nav[name][name]['ros__parameters']
    cm.update(robot_radius=.30,transform_tolerance=.5)
    cm['inflation_layer'].update(inflation_radius=.48,cost_scaling_factor=4.)
    for layer in ('voxel_layer','obstacle_layer'):
        if layer in cm:cm[layer]['scan']['topic']='/scan'
slam=yaml.safe_load((share/'slam_toolbox/config/mapper_params_online_async.yaml').read_text())
slam['slam_toolbox']['ros__parameters'].update(base_frame='base_link',scan_topic='/scan',use_sim_time=True,
    resolution=.05,minimum_travel_distance=.09,minimum_travel_heading=.10,minimum_time_interval=.15,
    map_update_interval=1.,max_laser_range=25.)
for name,doc in [('nav2',nav),('slam',slam)]:
    (dest/(name+'.yaml')).write_text(yaml.safe_dump(doc,sort_keys=False))
