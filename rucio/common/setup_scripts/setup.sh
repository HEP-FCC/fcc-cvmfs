#!/bin/bash
#!----------------------------------------------------------------------------
#!
#! setup.sh
#!
#!
#! History:
#!   15May25: G. Guerrieri: First version
#!
#!----------------------------------------------------------------------------

# Setup for Rucio client environment

# Determine shell type (bash/zsh) for path handling
shell_type="bash"
ps -o command= $$ 2>/dev/null | grep -q zsh && shell_type="zsh"

# Set RUCIO_HOME if not already set
if [ -z "$RUCIO_HOME" ]; then
    if [ "$shell_type" = "zsh" ]; then
        export RUCIO_HOME="$(cd "$(dirname "$0")" && pwd)"
    else
        export RUCIO_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    fi
    echo "INFO: Set RUCIO_HOME to $RUCIO_HOME"
fi

# Detect Python binary: respect RUCIO_PYTHONBIN if set, otherwise try python3 then python
if [ -z "${RUCIO_PYTHONBIN:-}" ]; then
    if command -v python3 >/dev/null 2>&1; then
        export RUCIO_PYTHONBIN="python3"
    elif command -v python >/dev/null 2>&1; then
        export RUCIO_PYTHONBIN="python"
    else
        echo "ERROR: No Python installation found in PATH. Please install Python >= 3.9."
        return 64
    fi
fi

if ! command -v "$RUCIO_PYTHONBIN" >/dev/null 2>&1; then
    echo "ERROR: Python binary '$RUCIO_PYTHONBIN' not found in PATH."
    return 64
fi

# Check Python meets the minimum version required by rucio-clients
min_ver=$(cat "$RUCIO_HOME/python-requires" 2>/dev/null || echo "3.9")
if ! "$RUCIO_PYTHONBIN" -c "
import sys
min = tuple(int(x) for x in '$min_ver'.split('.'))
sys.exit(0 if sys.version_info >= min else 1)
" 2>/dev/null; then
    echo "ERROR: $($RUCIO_PYTHONBIN -V 2>&1) does not meet the minimum requirement >= $min_ver"
    return 64
fi

# Find site-packages — version-independent since rucio-clients is pure Python
sitepkgs=$(find "$RUCIO_HOME/lib" -mindepth 2 -maxdepth 2 -name site-packages | head -1)
if [ -z "$sitepkgs" ]; then
    echo "ERROR: Could not locate site-packages in $RUCIO_HOME/lib. The installation may be corrupt."
    return 64
fi

# Update PATH and PYTHONPATH
export PATH="$RUCIO_HOME/bin:$PATH"
export PYTHONPATH="$sitepkgs:$PYTHONPATH"

# Clear the command hash table to ensure the shell uses the updated PATH
hash -r 2>/dev/null || true

# Optional: Bash autocompletion for rucio clients
if [ "$shell_type" = "bash" ]; then
    eval "$(register-python-argcomplete rucio 2>/dev/null)"
    eval "$(register-python-argcomplete rucio-admin 2>/dev/null)"
fi

export RUCIO_ACCOUNT="${RUCIO_ACCOUNT:-$(whoami)}"
export RUCIO_CONFIG="${RUCIO_CONFIG:-$RUCIO_HOME/rucio-fcc.cfg}"

echo "INFO: Rucio client environment is set up."
