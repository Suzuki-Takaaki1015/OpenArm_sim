# YCB attribution and preparation

Original dataset: **The YCB Object and Model Set**, Berk Calli, Arjun Singh,
Aaron Walsman, Siddhartha Srinivasa, Pieter Abbeel, Aaron M. Dollar.
Source: https://ycb-benchmarks.s3.amazonaws.com/index.html
Catalog: https://ycb-benchmarks.s3.amazonaws.com/data/objects.json
Retrieved 2026-09-16. Each archive URL and SHA-256 is in catalog.json.
Dataset license: **Creative Commons Attribution 4.0 International**:
https://creativecommons.org/licenses/by/4.0/
License legal text: https://creativecommons.org/licenses/by/4.0/legalcode

The original scans and our modified derivatives retain CC BY 4.0 attribution.
Eight completely generated proxies (023, 039, 046, 047, 063-c/e/f, 076) are
provided under CC0 1.0: https://creativecommons.org/publicdomain/zero/1.0/
They are labelled as proxies, not original YCB meshes. No endorsement implied.

Changes: bounding-box centre translated to origin; metric scale/orientation
retained for scans. Textures resized to 512x512. Visual UV coordinates retained.
Collision meshes generated with CoACD 1.0.14, trimesh 5.1.0, NumPy 2.2.6,
SciPy 1.18.1, fast-simplification 0.2.0, Pillow. These are preparation tools,
not additional runtime dependencies.

Default CoACD: real_metric=True, threshold 0.003 m; mug/plate/bowl/cups/skillet/
fork/spoon/knife/clamp 0.0015 m; max_convex_hull=64; resolution=3000;
mcts_iterations=60; mcts_nodes=15; preprocess_resolution=60; decimate=True;
max_ch_vertex=64; seed=7. Actual per-object result is retained in model.json.
Plate override: threshold=0.0005 m, max_convex_hull=128, preprocess_mode=off,
resolution=4000, mcts_iterations=40 (thin plate wall preserved).
Racquetball: convex hull of original ball, simplified to 512 faces, then convex
hull again. Toy airplane g/h: discard scan-platform triangles outside the
central 160 mm square, recenter, reconstruct 32 convex hulls, threshold 3 mm.
These incomplete scans remain labelled approximate.

Google 16k preferred, Berkeley processed used when unavailable. The official
catalog's 027-skillet uses the archive name 027_skillet_google_16k.tgz.
No raw RGB/RGB-D captures or temporary archives are included. Per-file SHA-256
hashes are in each model.json. Shape processing is approximate; rigid-body,
friction, mass-estimate, and inertia limitations are explained in YCB.md.

CoACD reference and algorithm source: https://github.com/SarahWeiii/CoACD
Mass source: Calli et al., ICAR 2015, Table I:
https://www.ri.cmu.edu/pub_files/2015/7/ICAR-FINAL.pdf
