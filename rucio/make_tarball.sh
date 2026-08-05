#!/usr/bin/env bash
# Copyright European Organization for Nuclear Research (CERN)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#                       http://www.apache.org/licenses/LICENSE-2.0
#
# Authors:
# - Giovanni Guerrieri, <giovanni.guerrieri@cern.ch>, 2025

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Defaults — override via CLI or environment
_default_version="$(awk -F': *' '/^rucio_version:/{gsub(/["'"'"']/, "", $2); print $2}' "$SCRIPT_DIR/config.yaml")"
RUCIO_VERSION="${1:-${RUCIO_VERSION:-$_default_version}}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

EXPORT_ENV_NAME=rucio

# Set locale settings
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

warn () {
  echo "WARNING: $*" >&2
}

# Derive major.minor from the selected Python binary
PY_MM="$("$PYTHON_BIN" -c 'import sys; print("{}.{}".format(*sys.version_info[:2]))')"

# Venv is created in a temp directory so it is not included in the tarball
VENV_DIR="$(mktemp -d)"
trap 'rm -rf "$VENV_DIR"' EXIT
ENV_PATH="${VENV_DIR}/${EXPORT_ENV_NAME}"

# Prepare workspace
BUILD_ROOT="$SCRIPT_DIR/$RUCIO_VERSION"
mkdir -p "$BUILD_ROOT"
cd "$BUILD_ROOT"
mkdir -p lib

echo "=== Building rucio-clients $RUCIO_VERSION ==="
echo "    Python: $("$PYTHON_BIN" --version)"

echo "Creating virtual environment"
"$PYTHON_BIN" -m venv "$ENV_PATH"

echo "Installing dependencies"
"$ENV_PATH/bin/pip" install --upgrade pip
"$ENV_PATH/bin/pip" install -U setuptools wheel
"$ENV_PATH/bin/pip" install "rucio-clients==${RUCIO_VERSION}"
"$ENV_PATH/bin/pip" install argcomplete
"$ENV_PATH/bin/pip" freeze

echo "Extracting Python version requirement"
"$ENV_PATH/bin/python" -c "
import importlib.metadata, re
req = importlib.metadata.metadata('rucio-clients').get('Requires-Python', '')
m = re.search(r'>=\s*(\d+\.\d+)', req)
print(m.group(1) if m else '3.9')
" > python-requires
echo " - Requires-Python: $(cat python-requires)"

echo "Consolidating site-packages"
LIB_ROOT="${ENV_PATH}/lib/python${PY_MM}"

# Ensure dogpile namespace package is properly initialized
DOGPILE_PATH="${LIB_ROOT}/site-packages/dogpile"
if [ -d "$DOGPILE_PATH" ]; then
  touch "$DOGPILE_PATH/__init__.py"
else
  warn "Dogpile package not found at $DOGPILE_PATH"
fi

if [ ! -d "$LIB_ROOT" ]; then
  warn "Expected lib directory $LIB_ROOT missing"
else
  mkdir -p "lib/python${PY_MM}"
  rsync -a "$LIB_ROOT"/ "lib/python${PY_MM}/"
fi

echo "General: Copying in bin/"
mkdir -p bin
cp "${ENV_PATH}/bin/rucio" bin/
cp "${ENV_PATH}/bin/rucio-admin" bin/
cp "${ENV_PATH}/bin/register-python-argcomplete" bin/

echo "General: Cleaning bin/"
if [ -f "$SCRIPT_DIR/common/rm_from_bin_folder.txt" ]; then
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    echo " - $file"
    rm -f "bin/$file"
  done < "$SCRIPT_DIR/common/rm_from_bin_folder.txt"
fi

echo "General: Adapting bin scripts"
for script in bin/*; do
  [ -f "$script" ] || continue
  tmpfile="$(mktemp)"
  {
    printf '#!/bin/bash\n'
    printf '# -*- coding: utf-8 -*-\n'
    printf '"exec" "$RUCIO_PYTHONBIN" "-u" "-Wignore" "$0" "$@"\n'
    tail -n +2 "$script" 2>/dev/null || true
  } > "$tmpfile"
  mv "$tmpfile" "$script"
  chmod +x "$script"
done

echo "General: Copying setup scripts"
cp -R "$SCRIPT_DIR"/common/setup_scripts/setup* .

echo "General: Copying config"
cp "$SCRIPT_DIR/rucio-fcc.cfg" .

echo "General: Creating archive"
tar zcf "$SCRIPT_DIR/rucio-clients-${RUCIO_VERSION}.tar.gz" *
echo " - $(ls -la "$SCRIPT_DIR/rucio-clients-${RUCIO_VERSION}.tar.gz")"

echo "General: DONE!"
