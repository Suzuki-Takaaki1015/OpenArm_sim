"""Rebuild bundled Livox reference asset from the pinned upstream CSV (offline).

Download scan_mode/mid360.csv at commit 1cce1073633a062b92e30243a4c2920e45551bb5
from https://github.com/Livox-SDK/livox_laser_simulation . Keep the MIT license.
The original Time/s column is ordinal; no physical timing is inferred from it.
"""
import argparse,hashlib
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser(description=__doc__);p.add_argument('csv',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
assert hashlib.sha256(args.csv.read_bytes()).hexdigest()=='aa1fc08b6a4400608dbd6ee832b7ea3a9c3c37197e734f60f58fe5abf762269a','Unexpected upstream CSV'
x=np.loadtxt(args.csv,delimiter=',',skiprows=1)
assert x.shape==(800000,3) and np.isfinite(x).all()
assert np.array_equal(x[:,0],np.arange(1,800001))
np.savez_compressed(args.output,angles_deg=x[:,1:].astype('<f4'))
print('SHA256',hashlib.sha256(args.output.read_bytes()).hexdigest())
