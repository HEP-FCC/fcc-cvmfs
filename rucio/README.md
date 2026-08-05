# rucio-clients tarball builder

Builds a self-contained `rucio-clients` tarball for deployment on CVMFS.

Based on the original implementation from [vre-hub/escape-cvmfs](https://github.com/vre-hub/escape-cvmfs/tree/main).

## Build

### Prerequisites

1. Install Python 3.x and `rsync`:

```bash
# RHEL/Alma/Rocky
dnf install python3 rsync

# Debian/Ubuntu
apt-get install python3 rsync
```

### Build the tarball

The default version is set in `config.yaml`. Build with it:

```bash
./make_tarball.sh
```

Build a specific version:

```bash
./make_tarball.sh 35.8.0
```

Or via environment variable:

```bash
RUCIO_VERSION=35.8.0 ./make_tarball.sh
```

The script creates a venv, installs `rucio-clients`, and produces `rucio-clients-<VERSION>.tar.gz`.

### CI

The GitHub Actions workflow triggers on pushes to `rucio/**` on `main`. You can also trigger it manually via `workflow_dispatch` and optionally specify a custom `rucio_version`.

## Deploy to CVMFS

```bash
./utils/rucio-cvmfs-updater.sh <GITHUB_TOKEN> <ARTIFACT_ID> [RUCIO_VERSION]
```

Use `--force` to overwrite an existing version:

```bash
./utils/rucio-cvmfs-updater.sh --force <GITHUB_TOKEN> <ARTIFACT_ID> 38.3.0
```

## Usage

After deployment, users source the setup script:

```bash
export RUCIO_HOME=/cvmfs/fcc.cern.ch/rucio/38.3.0
source $RUCIO_HOME/setup.sh
```
