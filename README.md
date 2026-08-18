# fcc-cvmfs

Scripts for managing components of the FCC software CVMFS directories at `/cvmfs/fcc.cern.ch`.

Inspired by [vre-hub/escape-cvmfs](https://github.com/vre-hub/escape-cvmfs/tree/main) implementation.

## Contents

### Rucio clients ([`rucio/`](rucio/))

Builds a self-contained `rucio-clients` tarball for use to eventually install on CVMFS. The default Rucio version is set in [`rucio/config.yaml`](rucio/config.yaml).
See [`rucio/README.md`](rucio/README.md) for full build, deploy, and usage instructions.

