# FIR: reproducible Python preprocessing environment

This guide covers Python packages for the **NAWM-CWARHM-MX preprocessing workflow** on the Digital Research Alliance of Canada's FIR cluster. It does **not** build the SUMMA or mizuRoute executables; those require a separate compiler/model-build environment.

## Design

- **FIR modules:** `StdEnv/2023`, `python/3.12.4`, `python-build-bundle/2026a`, `scipy-stack/2026a`, `gdal/3.9.1`, `mpi4py/4.0.3`, `libspatialindex/1.9.3`.
- **Local Python packages:** `virtualenv --no-download --system-site-packages` and `pip --no-index` against the FIR wheelhouse; requested versions are in [`requirements_fir.in`](../requirements_fir.in).
- **Special case—netCDF4 1.7.4 Python binding:** The available Python 3.12 wheel was linked to MPI NetCDF/HDF5, causing a native-library clash with Rasterio (which uses serial NetCDF/HDF5). The setup builds *only the Python binding* against serial NetCDF 4.9.2 and HDF5 1.14.2 already provided by FIR modules. It does not build/download NetCDF C or HDF5.
- **PROJ data:** `load_nwam_fir.sh` determines the `proj.db` directory matching the PROJ native library linked to the installed PyProj wheel. This avoids an incorrect `proj.db` selection when GDAL uses a different native PROJ version.

The configuration was verified on FIR on **30 October 2026** with Python 3.12.4, Rasterio 1.5.0, netCDF4 1.7.4 (serial), GDAL 3.9.1 and a working EPSG transformation. Module and wheelhouse availability may change over time; review the pinned versions when updating the environment.

## First-time installation (each user)

Clone or open the repository on FIR. The following example assumes you are already in the repository's root directory:

```bash
cd /path/to/NAWM-CWARHM-MX
```

Request an interactive allocation before compiling (follow your allocation's Slurm usage policy):

```bash
salloc --time=00:45:00 --cpus-per-task=2 --mem=8G
```

Once your prompt is on a compute node, run:

```bash
bash setup_nwam_fir.sh
```

The script will:

1. Load the FIR modules listed above.
2. Create `~/virtual-envs/nwam-fir` using module-visible site packages.
3. Install wheelhouse packages and build tools using `pip --no-index`.
4. Reuse a cached `netcdf4-python` release checkout if present; otherwise fetch upstream tag `v1.7.4rel` once from GitHub. GitHub access is required only on this cache miss. If compute nodes cannot reach GitHub, clone this source once from a login node to the build-cache path before running setup on a compute node (commands below). This is **source code only**, not additional native NetCDF/HDF5 installations.
5. Build and install serial netCDF4 1.7.4, check the native-library linkage, and run import, coordinate, NetCDF I/O and GeoTIFF I/O tests.

If outbound GitHub access is blocked on compute nodes, perform this **source-code fetch only** on a login node first:

```bash
mkdir -p "${SCRATCH:-$HOME/scratch}/nwam-netcdf4-build"
git clone --depth 1 --branch v1.7.4rel \
    https://github.com/Unidata/netcdf4-python.git \
    "${SCRATCH:-$HOME/scratch}/nwam-netcdf4-build/netcdf4-python"
```

Then return to the compute-node allocation for `bash setup_nwam_fir.sh`. The setup script uses the existing source clone rather than downloading again.

The setup script intentionally stops if the target virtual environment already exists rather than overwriting the user's working environment. For existing environments, see **Existing FIR installations** below.

When finished, exit the compute allocation normally and activate the environment in any new shell:

```bash
cd /path/to/NAWM-CWARHM-MX
source load_nwam_fir.sh
```

Verify at any time:

```bash
python 0_tools/check_nwam_fir.py
python -m pip check
```

## Existing FIR installations

Users who already followed the manual setup and validated the serial netCDF4 build **should not rerun** `setup_nwam_fir.sh`. They can source the loader and run the smoke test. The verified environment can be reused in new interactive or Slurm job shells.

```bash
source load_nwam_fir.sh
python 0_tools/check_nwam_fir.py
```

If a user has an incomplete or incompatible environment, back it up or choose a **different** environment name before running a new setup (do not delete an environment merely to make the setup script run):

```bash
NWAM_FIR_VENV="$HOME/virtual-envs/nwam-fir-new" bash setup_nwam_fir.sh
```

Activate that alternate environment by setting the same variable:

```bash
NWAM_FIR_VENV="$HOME/virtual-envs/nwam-fir-new" source load_nwam_fir.sh
```

The build cache can be relocated with `NWAM_FIR_BUILD_DIR`; an existing upstream source checkout can be reused with `NWAM_FIR_NETCDF4_SOURCE`.

## In batch jobs

Load the Python environment inside the Slurm job shell **before** calling Python:

```bash
#!/usr/bin/env bash
#SBATCH --time=00:30:00
#SBATCH --mem=4G

cd /path/to/NAWM-CWARHM-MX
source load_nwam_fir.sh
python 0_tools/check_nwam_fir.py
```

Actual preprocessing jobs should replace the smoke-test command with the appropriate workflow stage and must use the correct FIR input/output data roots. Examples: `/project/rrg-mclark/datasets/CAMELS_SPAT_MX/outputs/` for available source basin exports and `/project/rrg-mclark/datasets/CAMELS_SPAT_MX_Model/` for generated model domains, subject to access permissions and the repository's control files.

## What is and is not stored in Git

Commit the scripts, `requirements_fir.in`, validation test and documentation. **Do not commit** virtualenv directories, the locally compiled wheel, source build caches, or basin data. `requirements_fir.txt` may be kept as a *snapshot* produced by `pip freeze --local` from a validated environment; it is not the module-first bootstrap recipe and should not be used to recreate serial netCDF4 by itself.

The ARC Conda workflow remains separate: see the [repository README](../README.md) and the existing ARC environment YAML and shell scripts. Do not use ARC's `update_nwam_env.sh` on FIR.

## Diagnostics

If imports fail:

```bash
source load_nwam_fir.sh
python -m pip check
python 0_tools/check_nwam_fir.py
```

If netCDF4 fails after Rasterio, inspect its extension dependencies:

```bash
SO="$(find "$VIRTUAL_ENV/lib" -type f -path '*/site-packages/netCDF4/_netCDF4*.so' -print -quit)"
ldd "$SO" | grep -E 'netcdf|hdf5|mpi'
nm -D "$SO" | grep -E 'ompi_|MPI_' || echo 'No direct MPI symbols'
```

The expected configuration is **serial** NetCDF and HDF5, with no direct MPI references in the Python netCDF4 extension. In ordinary Python code, `mpi4py` may still be used for independent parallel tasks.

If an EPSG lookup fails, confirm that the loader set `PROJ_DATA` and that `"$PROJ_DATA/proj.db"` exists. Do not arbitrarily replace the PROJ database path with `EBROOTPROJ` when the linked PyProj extension uses a different native PROJ version.
