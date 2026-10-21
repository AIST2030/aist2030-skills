#!/usr/bin/env bash
# AIST2030免费模型智能管家 一键安装（macOS/Linux 便携版）
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
WB="$HOME/.workbuddy"

echo "=========================================="
echo " AIST2030免费模型智能管家 - 安装程序"
echo "=========================================="

# 1. Node.js
NODE_EXE="$WB/binaries/node/versions/22.22.2-6/node.exe"
[ -f "$NODE_EXE" ] || NODE_EXE="$(command -v node || true)"
[ -n "$NODE_EXE" ] || { echo "[X] 未找到 Node.js，请先安装 WorkBuddy 或 Node.js 16+"; exit 1; }
echo "[1/5] Node.js 就绪: $NODE_EXE"

# 2. WorkBuddy
[ -d "$WB" ] || { echo "[X] 未检测到 WorkBuddy 环境，请先安装并启动一次 WorkBuddy"; exit 1; }
echo "[2/5] WorkBuddy 环境就绪"

# 3. 网关
GWDIR="$WB/free-model-gateway"
mkdir -p "$GWDIR"
[ -d "$SRC/gateway" ] && cp -r "$SRC/gateway/." "$GWDIR/"
[ -f "$GWDIR/gateway.js" ] || { echo "[X] 网关文件缺失"; exit 1; }
echo "[3/5] 网关文件就绪: $GWDIR"

# 4. Skill 文件
SKPATH="$WB/skills/aist2030-model-manager"
mkdir -p "$SKPATH"
cp -f "$SRC/SKILL.md" "$SRC/main.js" "$SKPATH/"
[ -d "$SRC/docs" ] && cp -r "$SRC/docs" "$SKPATH/"
[ -d "$SRC/references" ] && cp -r "$SRC/references" "$SKPATH/"
echo "[4/5] Skill 文件就绪: $SKPATH"

# 5. 一键配置
echo "[5/5] 正在自动配置..."
cd "$SKPATH"
"$NODE_EXE" main.js configure

echo ""
echo "=========================================="
echo " 安装完成！打开 http://127.0.0.1:8787 粘贴免费 Key 即可"
echo "=========================================="
