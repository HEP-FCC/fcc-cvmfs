# fcc-cvmfs

Software packages deployed on the FCC CVMFS repository at `/cvmfs/fcc.cern.ch`.

Based on the original [vre-hub/escape-cvmfs](https://github.com/vre-hub/escape-cvmfs/tree/main) implementation.

## Repository structure

```
rucio/                        # Rucio clients tarball builder
  config.yaml                 # Default Rucio version (single source of truth)
  make_tarball.sh             # Builds the rucio-clients tarball
  rucio-fcc.cfg               # Rucio client config for FCC (bundled in tarball)
  common/
    rm_from_bin_folder.txt    # Binaries to strip from the tarball's bin/
    setup_scripts/
      setup.sh                # Sourced by users to set up the Rucio environment
  utils/
    rucio-cvmfs-updater.sh    # Deploys a built tarball to CVMFS
.github/workflows/
  build_rucio_tarball.yaml    # CI: builds the tarball and uploads it as an artifact
```

## Key facts

- **CVMFS mount**: `/cvmfs/fcc.cern.ch`
- **GitHub repo**: `davidlange6/fcc-cvmfs`
- **Default Rucio version**: set in `rucio/config.yaml`
- **Auth**: OIDC (`oidc_issuer = fcc`); the CA bundle is shared from `/cvmfs/sw.escape.eu`
- `rucio-clients` is pure Python — no compiled extensions, so the tarball works with any Python >= 3.9

## Rucio workflow

1. **Build**: CI runs `make_tarball.sh` via `build_rucio_tarball.yaml` and uploads the tarball as a GitHub Actions artifact. Can also be triggered manually with a custom version via `workflow_dispatch`.
2. **Deploy**: run `rucio/utils/rucio-cvmfs-updater.sh` with a GitHub token and artifact ID to publish to CVMFS.
3. **Use**: users source `setup.sh` from the installed CVMFS path.

## Bumping the Rucio version

Edit `rucio/config.yaml` — both `make_tarball.sh` and `rucio-cvmfs-updater.sh` read the default from there.
