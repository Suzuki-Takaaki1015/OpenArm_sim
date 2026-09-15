from pathlib import Path
import os
import yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, RegisterEventHandler, EmitEvent
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

CONFIG=Path('/opt/openarm/config')
def load(name):return yaml.safe_load((CONFIG/name).read_text())
def params():
    return {'robot_description':(CONFIG/'openarm.urdf').read_text(), 'robot_description_semantic':(CONFIG/'openarm.srdf').read_text(), 'robot_description_kinematics':load('kinematics.yaml'),'robot_description_planning':load('joint_limits.yaml'),'planning_pipelines':['ompl'],'default_planning_pipeline':'ompl','ompl':load('ompl.yaml'),'moveit_controller_manager':'moveit_simple_controller_manager/MoveItSimpleControllerManager','moveit_simple_controller_manager':load('moveit_controllers.yaml'),'trajectory_execution.allowed_execution_duration_scaling':2.0,'trajectory_execution.allowed_goal_duration_margin':10.0,'trajectory_execution.allowed_start_tolerance':0.05,'publish_robot_description':True,'publish_robot_description_semantic':True,'publish_planning_scene':True,'publish_geometry_updates':True,'publish_state_updates':True,'publish_transforms_updates':True,'use_sim_time':True}

def generate_launch_description():
    gui=LaunchConfiguration('gui');config=params()
    # MuJoCo is the sole simulation clock source. Both modes use identical physics.
    sim=ExecuteProcess(cmd=['python','/opt/openarm/app/bridge.py'],additional_env={'OPENARM_GUI':gui},output='screen')
    cm=Node(package='controller_manager',executable='ros2_control_node',parameters=[{'robot_description':config['robot_description']},str(CONFIG/'controllers.yaml')],output='screen')
    rsp=Node(package='robot_state_publisher',executable='robot_state_publisher',parameters=[{'robot_description':config['robot_description'],'use_sim_time':True}],output='screen')
    move=Node(package='moveit_ros_move_group',executable='move_group',parameters=[config],output='screen')
    spawn=Node(package='controller_manager',executable='spawner',arguments=['joint_state_broadcaster','left_arm_controller','right_arm_controller','left_gripper_controller','right_gripper_controller','--controller-manager-timeout','120','--switch-timeout','120','--activate-as-group'],output='screen')
    rviz=Node(package='rviz2',executable='rviz2',arguments=['-d','/opt/openarm/app/openarm.rviz'],parameters=[config],condition=IfCondition(gui),output='screen')
    camera=ExecuteProcess(cmd=['python','/opt/openarm/app/camera_node.py'],output='screen')
    objects=ExecuteProcess(cmd=['python','/opt/openarm/app/object_scene_sync.py'],output='screen')
    panel=ExecuteProcess(cmd=['python','/opt/openarm/app/scene_panel.py'],condition=IfCondition(gui),output='screen')
    ready=ExecuteProcess(cmd=['python','/opt/openarm/app/wait_ready.py'],output='screen')
    def after_ready(event, context):
        return [spawn] if event.returncode == 0 else [EmitEvent(event=Shutdown(reason='MuJoCo startup failed'))]
    actions=[DeclareLaunchArgument('gui',default_value='false'),sim,rsp,cm,move,rviz,camera,objects,ready,RegisterEventHandler(OnProcessExit(target_action=ready,on_exit=after_ready))]
    for critical in [sim,cm,move,objects]:
        actions.append(RegisterEventHandler(OnProcessExit(target_action=critical,on_exit=[EmitEvent(event=Shutdown(reason='Required node exited'))])))
    return LaunchDescription(actions)
