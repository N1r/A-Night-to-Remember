#!/bin/bash

# Kimi_V One-Key Discovery & Processing Script (Refactored)
# This script automates the 3-stage workflow: Pre -> Mid -> Post processing.

# 1. Resolve Project Root and Python
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# 添加 2_mid_processing 到 PYTHONPATH 确保 core 模块可导入
export PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT:$PROJECT_ROOT/2_mid_processing

# 确保包含通过 uv 等工具安装在 ~/.local/bin 的可执行文件（如 biliup）
export PATH="$HOME/.local/bin:$PATH"

# 优先查找当前项目目录下的虚拟环境 python
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
if [ -f "$VENV_PYTHON" ]; then
    PYTHON_CMD="$VENV_PYTHON"
else
    PYTHON_CMD="python"
fi

echo "===================================================="
echo "🚀 Kimi_V Three-Stage Workflow Starting"
echo "Project Root: $PROJECT_ROOT"
echo "Using Python: $PYTHON_CMD"
echo "===================================================="

# 2. Step 0: Environment Cleanup
echo "--- [Step 0/3] Cleaning Environment ---"
"$PYTHON_CMD" "$PROJECT_ROOT/3_post_processing/clean_all.py"

# 3. Step 1: Pre-processing
echo ""
echo "--- [Step 1/3] Pre-processing (Fetch & Score) ---"
"$PYTHON_CMD" "$PROJECT_ROOT/1_pre_processing/workflow_1_pre.py"

if [ $? -ne 0 ]; then
    echo "❌ Pre-processing failed."
    exit 1
fi

# 3. Step 2: Mid-processing
echo ""
echo "--- [Step 2/3] Mid-processing (ASR, Trans, Align) ---"
"$PYTHON_CMD" "$PROJECT_ROOT/2_mid_processing/workflow_2_mid.py"

if [ $? -ne 0 ]; then
    echo "❌ Mid-processing failed."
    exit 1
fi

# 4. Step 3: Post-processing
echo ""
echo "--- [Step 3/3] Post-processing (FFmpeg, Cover, Upload) ---"
"$PYTHON_CMD" "$PROJECT_ROOT/3_post_processing/workflow_3_post.py"

if [ $? -eq 0 ]; then
    echo ""
    echo "===================================================="
    echo "✨ All processing completed! ✨"
    echo "Check 'output/processed' for your results."
    echo "===================================================="
else
    echo "❌ Batch processing failed."
    exit 1
fi
