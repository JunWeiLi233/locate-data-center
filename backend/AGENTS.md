# Imported county screening backend

`dataclocator/` contains the existing, separately packaged county Monte Carlo backend. It remains independent of `src/dc_locator`, which is the teammate's accepted grid model. This integration is user-authorized; no earlier grid phase or model math is replaced.

Comment every created or modified function and logical section. Keep Python 3.13 dependencies and data roots separate from the grid model's Python 3.12 environment. Do not commit raw/processed datasets, outputs, simulation arrays, virtual environments, secrets or caches. Source manifests, source code, configurations and tests are reviewable inputs; acquire/preprocess official data locally.
