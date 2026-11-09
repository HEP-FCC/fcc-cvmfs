# fcc-cvmfs

Software packages deployed on the FCC CVMFS repository at `/cvmfs/fcc.cern.ch`.

Based on the original [vre-hub/escape-cvmfs](https://github.com/vre-hub/escape-cvmfs/tree/main) implementation.

## Repository structure

```
fcc_data/                     # Data file registry (ONNX models, Delphes cards, etc.)
  README.md                   # Submission instructions and file format
  <category>/[<subcategory>/]
    summary_<package>.yml     # Permanent append-only record of each registered package
production_bundles/           # Production software bundle registry (tar archives)
  README.md                   # Submission instructions and file format
  <category>/[<subcategory>/]
    summary_<bundle>.yml      # Permanent append-only record of each registered bundle
rucio/                        # Rucio clients tarball builder
  config.yaml                 # Default Rucio version (single source of truth)
  make_tarball.sh             # Builds the rucio-clients tarball
  rucio-fcc.cfg               # Rucio client config for FCC (bundled in tarball)
  common/
    rm_from_bin_folder.txt    # Binaries to strip from the tarball's bin/
    setup_scripts/
      setup.sh                # Sourced by users to set up the Rucio environment
.github/workflows/
  build_rucio_tarball.yaml    # CI: builds the tarball and uploads it as an artifact
  process_data.yaml           # CI: validates/checksums fcc_data submissions on merge
  process_bundles.yaml        # CI: validates/checksums production_bundles submissions on merge
.github/scripts/
  process_data.py             # Logic for process_data.yaml
  process_bundles.py          # Logic for process_bundles.yaml (supports local tarballs + tar listings)
```

## Key facts

- **CVMFS mount**: `/cvmfs/fcc.cern.ch`
- **GitHub repo**: `davidlange6/fcc-cvmfs`
- **Default Rucio version**: set in `rucio/config.yaml`
- **Auth**: OIDC (`oidc_issuer = fcc`); the CA bundle is shared from `/cvmfs/sw.escape.eu`
- `rucio-clients` is pure Python — no compiled extensions, so the tarball works with any Python >= 3.9

## Rucio workflow

1. **Build**: CI runs `make_tarball.sh` via `build_rucio_tarball.yaml` and uploads the tarball as a GitHub Actions artifact. Can also be triggered manually with a custom version via `workflow_dispatch`.

## Bumping the Rucio version

Edit `rucio/config.yaml` — both `make_tarball.sh` and `rucio-cvmfs-updater.sh` read the default from there.
