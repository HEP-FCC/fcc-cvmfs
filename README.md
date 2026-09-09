# fcc-cvmfs

Scripts for managing components of the FCC software CVMFS directories at `/cvmfs/fcc.cern.ch`.

Inspired by [vre-hub/escape-cvmfs](https://github.com/vre-hub/escape-cvmfs/tree/main) implementation.

## Contents

### FCC Models ([`fcc_models/`](fcc_models/))

Tracks data files (ONNX models, Delphes cards, etc.) available on the FCC CVMFS repository. To register a new model version, add a YAML submission file to `fcc_models/` and open a pull request. A validation check runs automatically on every PR; once merged, the summary registry is updated and the submission file is removed.

See [`fcc_models/README.md`](fcc_models/README.md) for the file format and full submission instructions.

### Rucio clients ([`rucio/`](rucio/))

Builds a self-contained `rucio-clients` tarball for use to eventually install on CVMFS. The default Rucio version is set in [`rucio/config.yaml`](rucio/config.yaml).
See [`rucio/README.md`](rucio/README.md) for full build, deploy, and usage instructions.
