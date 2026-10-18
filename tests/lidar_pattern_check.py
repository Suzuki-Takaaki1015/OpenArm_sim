"""Bundled reference provenance and deterministic scan-window regressions."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
app=Path('/opt/openarm/app') if Path('/opt/openarm/app').exists() else Path(__file__).resolve().parents[1]/'docker/app'
sys.path.insert(0,str(app))
from lidar_scan import sample_directions,window_start,reference_angles,REFERENCE_SIZE,SAMPLE_RATE
meta=json.loads((app/'lidar_assets/SCAN_SOURCE.json').read_text())
assert hashlib.sha256((app/'lidar_assets/mid360_scan.npz').read_bytes()).hexdigest()==meta['asset_sha256']
assert REFERENCE_SIZE==meta['rows']==800000 and SAMPLE_RATE==200000
# CSV zenith is measured from +Z; converting it as elevation would point backwards.
a=reference_angles()[0];el=-7+(90-a[1]+7.2123)*59/(52.164+7.2123);az=np.radians(a[0]);el=np.radians(el)
expected=[np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)]
assert np.allclose(sample_directions(1,0,1)[0],expected,atol=1e-12)
r=sample_directions(40000,0);later=sample_directions(40000,40000)
assert np.allclose(np.linalg.norm(r,axis=1),1)
elev=np.degrees(np.arcsin(r[:,2]));assert elev.min()>=-7-1e-9 and elev.max()<=52+1e-9
assert not np.array_equal(r,later)
# Row order survives frame boundaries and reference-buffer wrap.
joined=np.r_[sample_directions(700,799800,700),sample_directions(300,800500,300)]
assert np.array_equal(joined,sample_directions(1000,799800,1000))
assert np.array_equal(r,sample_directions(40000,800000))
# Density switch and missed callbacks use simulation time, not output-frame count.
assert window_start(.2,.2)==0
assert window_start(1.,.2)==160000
assert window_start(1.8,.2)==320000
for count in (800,8000,40000):
    out=sample_directions(count,window_start(1.,.2))
    assert len(out)==count and np.array_equal(out,sample_directions(count,160000))
# Reduced density selects vendor samples rather than interpolating/fabricating rays.
full={tuple(v) for v in sample_directions(1000,100000,1000)}
assert all(tuple(v) in full for v in sample_directions(64,100000,1000))
for args in [(0,0,100),(101,0,100),(1,0,0)]:
    try:sample_directions(*args)
    except ValueError:pass
    else:raise AssertionError(args)
print('PASS scan source hash, axes/FOV, sequence continuity/wrap, simulation-time phase, density thinning')
