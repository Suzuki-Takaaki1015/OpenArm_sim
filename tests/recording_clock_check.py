import os
assert os.environ.get('OPENARM_ISOLATED_TEST')=='1'
import json
import socket
import time
from recording import Controller,ROOT
controller=Controller();controller.start('external_restart')
deadline=time.monotonic()+25
while time.monotonic()<deadline:
    path=ROOT/'external_restart/openarm.json'
    if path.exists() and json.loads(path.read_text())['state']=='recording':break
    time.sleep(.1)
else:raise AssertionError('start')
time.sleep(2)
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
    client.settimeout(2);client.connect('/tmp/openarm-supervisor.sock');client.sendall(b'restart\n');assert client.recv(64).strip()==b'restarting'
deadline=time.monotonic()+30
while controller.active() and time.monotonic()<deadline:time.sleep(.1)
assert not controller.active()
data=json.loads(path.read_text())
assert data['state']=='error' and data['stop_reason'] in ('clock_reset','clock_timeout') and data['bag_finalized'],data
print('PASS EXTERNAL RESTART PROTECTION',data['stop_reason'],flush=True)
