#!/usr/bin/env python3
"""Install/update this checkout's shell helpers without duplicating bashrc entries."""
from pathlib import Path
import shutil
import datetime
root=Path(__file__).resolve().parent
source=root/'scripts/openarm-aliases.bash'
target=Path.home()/'.config/openarm/aliases.bash'
target.parent.mkdir(parents=True,exist_ok=True)
shutil.copyfile(source,target)
shutil.copyfile(source.with_name('oa_code.py'),target.with_name('oa_code.py'))
bashrc=Path.home()/'.bashrc'
s=bashrc.read_text() if bashrc.exists() else ''
line='[ ! -f "$HOME/.config/openarm/aliases.bash" ] || . "$HOME/.config/openarm/aliases.bash"'
if line not in s:
    if bashrc.exists():shutil.copyfile(bashrc,bashrc.with_name('.bashrc.openarm-backup-'+datetime.datetime.now().strftime('%Y%m%d%H%M%S')))
    bashrc.write_text(s+'\n# OpenArm development helpers\n'+line+'\n')
print('Installed: oa, oa-code, oa-ros, oa-scene, oa-logs. Run: source ~/.bashrc')
