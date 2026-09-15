"""Connect versioned source to the persistent ROS development workspace."""
from pathlib import Path
import json
root=Path('/workspaces/OpenArm_dev');repo=Path('/workspaces/OpenArm_sim')
if root.is_dir() and repo.is_dir():
    (root/'src').mkdir(exist_ok=True)
    for link,target in [(root/'src/openarm_demos',repo/'docker/demos/openarm_demos'),(root/'environment',repo)]:
        if not link.exists() and not link.is_symlink():link.symlink_to(target,target_is_directory=True)
        elif link.is_symlink() and link.resolve()!=target.resolve():raise RuntimeError(f'Unexpected workspace link: {link}')
    (root/'.vscode').mkdir(exist_ok=True)
    p=root/'.vscode/settings.json';cfg=json.loads(p.read_text()) if p.exists() else {}
    cfg.setdefault('files.exclude',{})['**/.openarm']=True
    cfg.setdefault('python.defaultInterpreterPath','/opt/venv/bin/python')
    p.write_text(json.dumps(cfg,indent=2)+'\n')
    (root/'DEMO_GUIDE.md').write_text('# OpenArm demos\n\nEdit src/openarm_demos/openarm_demos/. These are the same versioned files under environment/docker/demos/.\n\nBuild: colcon build --symlink-install --packages-select openarm_demos\n\nThen: source install/setup.bash\n\nRun: ros2 run openarm_demos bimanual_demo (or grasp_demo).\n\nThe GUI re-sources this overlay each time a demo starts. Runtime bridge source is in environment/docker/app; rebuild its Docker image after editing it.\n')
