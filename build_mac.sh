#!/usr/bin/env bash
set -euo pipefail

# 用法：将整个项目拷到 macOS 后，在项目根目录执行  bash build_mac.sh
# 可用环境变量覆盖默认值：PYTHON_BIN=/usr/bin/python3 VENV_DIR=.venv-mac

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv-mac}"
DIST_DIR="RT_Predictor_mac"

if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip

pip install numpy pandas
pip install dgl -f https://data.dgl.ai/wheels/repo.html
pip install torch deepchem rdkit pyinstaller

rm -rf "$DIST_DIR" build_rt_mac
pyinstaller --noconfirm --clean \
    --distpath "$DIST_DIR" \
    --workpath build_rt_mac \
    RT_Predictor_mac.spec

codesign --force --deep --sign - "$DIST_DIR/RT_Predictor.app" || true

echo
echo "构建完成: $(pwd)/$DIST_DIR/RT_Predictor.app"
