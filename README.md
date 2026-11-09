# fcc-cvmfs

Scripts for managing components of the FCC software CVMFS directories at `/cvmfs/fcc.cern.ch`.

Inspired by [vre-hub/escape-cvmfs](https://github.com/vre-hub/escape-cvmfs/tree/main) implementation.

## Contents

### FCC Data ([`fcc_data/`](fcc_data/))

Tracks data files (ONNX models, Delphes cards, etc.) available on the FCC CVMFS repository. To register a new version, add a YAML submission file to `fcc_data/` and open a pull request. A validation check runs automatically on every PR; once merged, the summary registry is updated and the submission file is removed.

See [`fcc_data/README.md`](fcc_data/README.md) for the file format and full submission instructions.

### Production Bundles ([`production_bundles/`](production_bundles/))

Tracks production software bundles (tar archives) available on the FCC CVMFS repository. Bundles may be submitted via URL or by committing a tarball (< 50 MB) directly into the PR — the CI removes the blob from git history after merge. A file listing (`tar -tvf`) is captured in the artifact for each bundle so reviewers can inspect archive contents.

See [`production_bundles/README.md`](production_bundles/README.md) for the file format and submission instructions.

### Rucio clients ([`rucio/`](rucio/))

Builds a self-contained `rucio-clients` tarball for use to eventually install on CVMFS. The default Rucio version is set in [`rucio/config.yaml`](rucio/config.yaml).
See [`rucio/README.md`](rucio/README.md) for full build, deploy, and usage instructions.
