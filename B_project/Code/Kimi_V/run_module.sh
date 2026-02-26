#!/bin/bash

# Script to run a single module for debugging
# Usage: ./run_module.sh core/_7_1_ass_into_vid.py

if [ -z "$1" ]; then
    echo "Usage: ./run_module.sh <path_to_module.py>"
    exit 1
fi

PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT
CONDA_PYTHON="/home/ADing/miniconda3/envs/videolingo/bin/python"

MODULE_PATH=$1
# Convert path to module name if dot notation is preferred, but simple path works with -m or direct
# We'll run it directly as a script but with PYTHONPATH set

echo "Running module: $MODULE_PATH ..."
"$CONDA_PYTHON" "$MODULE_PATH"
