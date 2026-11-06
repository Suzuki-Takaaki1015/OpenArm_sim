"""Navigation state, maps and launch entry points for mobile mode."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

WORK = Path('/workspaces/OpenArm_dev/navigation')
MAPS = WORK/'maps'
MODE = WORK/'mode.json'

def room_id():
    from room_layout import ACTIVE, EMPTY, read
    layout=read(ACTIVE) if ACTIVE.exists() else EMPTY
    layout.pop('library_name',None)  # Map compatibility depends on geometry.
    for furniture in layout['items']:
        furniture.pop('objects',None)  # Movable tabletop objects do not define a floor map.
    return hashlib.sha256(json.dumps(layout,sort_keys=True).encode()).hexdigest()

def setup():
    WORK.mkdir(parents=True,exist_ok=True)
    MAPS.mkdir(exist_ok=True)
    for name in ('slam.yaml','nav2.yaml'):
        path=WORK/name
        source = Path('/opt/happy/navigation')/name
        if not path.exists():
            shutil.copyfile(source,path)
        elif name == 'nav2.yaml' and not path.is_symlink():
            # Exact signatures of the untouched 0.24 and 0.40 m/s DWB defaults.
            previous = {
                '8254c752edc3065650c6557f2d06391f6569ca37a2143a0ef8164c32f8d51d75',
                '42b22b3b635b5857831a3c8a937b0a5b8eebf07a5370697a589bca918297c561',
            }
            if hashlib.sha256(path.read_bytes()).hexdigest() in previous:
                with tempfile.NamedTemporaryFile(dir=WORK,delete=False) as tmp:
                    new_path = Path(tmp.name)
                try:
                    shutil.copyfile(source,new_path)
                    shutil.copymode(path,new_path)
                    os.replace(new_path,path)
                finally:
                    new_path.unlink(missing_ok=True)

def directory(name):
    if not isinstance(name,str) or not re.fullmatch(r'[\w-]{1,64}',name):
        raise ValueError('地図名には文字・数字・ハイフン・下線を使用してください。')
    return MAPS/name

def space(room):
    return WORK/'by_room'/room

def map_paths(room):
    paths={}
    for root in (MAPS,space(room)/'maps'):
        for yaml_path in root.glob('*/map.yaml'):
            marker=yaml_path.parent/'room.id'
            if marker.is_file() and marker.read_text()==room:
                paths[yaml_path.parent.name]=yaml_path
    return paths

def selected():
    room=room_id()
    state_file=space(room)/'mode.json'
    if not state_file.exists():state_file=MODE  # Read the selection made by older versions.
    if state_file.exists():
        state=json.loads(state_file.read_text())
        if state.get('room')==room:
            return map_paths(room).get(state.get('map'))
    return None

def choose(name):
    room=room_id()
    if name is not None and name not in map_paths(room):
        raise ValueError('現在の環境で保存した地図を選んでください。')
    root=space(room)
    root.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=root,mode='w',delete=False) as f:
        json.dump({'map':name,'room':room},f)
    os.replace(f.name,root/'mode.json')

def save(name):
    room=room_id()
    dest=space(room)/'maps'/directory(name).name
    if name in map_paths(room) or dest.exists():raise ValueError('同名の地図があります。別の名前で保存してください。')
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as stage:
        bundle=Path(stage)/'bundle'
        bundle.mkdir()
        subprocess.run(['ros2','run','nav2_map_server','map_saver_cli','-f',str(bundle/'map'),
                        '--ros-args','-p','use_sim_time:=true','-p','save_map_timeout:=10.0'],check=True,timeout=20)
        if not (bundle/'map.yaml').is_file() or room!=room_id():raise RuntimeError('保存中に環境が変化しました。')
        (bundle/'room.id').write_text(room)
        bundle.rename(dest)

def actions(gui):
    from ament_index_python.packages import get_package_share_directory
    from launch.actions import IncludeLaunchDescription
    from launch.launch_description_sources import PythonLaunchDescriptionSource
    from launch.conditions import IfCondition
    from launch_ros.actions import Node
    def include(pkg,file,**args):
        path=Path(get_package_share_directory(pkg))/'launch'/file
        return IncludeLaunchDescription(PythonLaunchDescriptionSource(str(path)),
            launch_arguments=dict(use_sim_time='true',autostart='true',use_composition='False',**args).items())
    setup()
    nav=str(WORK/'nav2.yaml')
    path=selected()
    localization=(include('nav2_bringup','localization_launch.py',params_file=nav,map=str(path)) if path else
                  include('slam_toolbox','online_async_launch.py',slam_params_file=str(WORK/'slam.yaml')))
    return [localization,include('nav2_bringup','navigation_launch.py',params_file=nav),
        Node(package='rviz2',executable='rviz2',name='navigation_rviz',arguments=['-d','/opt/happy/navigation/operations.rviz'],
             parameters=[{'use_sim_time':True}],condition=IfCondition(gui),output='screen')]
