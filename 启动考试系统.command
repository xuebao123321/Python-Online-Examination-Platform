#!/bin/bash

# ==========================================
#  🐍 Python 在线考试系统 — 一键启动脚本
#  适用平台：macOS
#  用法：双击此文件即可启动
# ==========================================

# 切换到脚本所在目录（解决双击时工作目录不是脚本目录的问题）
cd "$(dirname "$0")"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║   🐍 Python 在线考试系统            ║"
echo "  ║   正在检查运行环境...               ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ---- 1. 检查 Python3 ----
if command -v python3 &> /dev/null; then
    echo "  ✅ 已找到 Python3：$(python3 --version)"
else
    echo "  ❌ 未找到 Python3，请先安装 Python3。"
    echo "  📥 下载地址：https://www.python.org/downloads/"
    echo ""
    echo "  按任意键退出..."
    read -n 1
    exit 1
fi

# ---- 2. 检查 / 安装 streamlit ----
echo "  🔍 检查 streamlit 是否已安装..."
if python3 -c "import streamlit" &> /dev/null; then
    echo "  ✅ streamlit 已安装"
else
    echo "  📥 正在安装 streamlit（首次使用需要几分钟）..."
    python3 -m pip install streamlit --quiet
    if [ $? -eq 0 ]; then
        echo "  ✅ streamlit 安装成功！"
    else
        echo "  ❌ streamlit 安装失败，请检查网络连接后重试。"
        echo ""
        echo "  按任意键退出..."
        read -n 1
        exit 1
    fi
fi

# ---- 3. 启动考试系统 ----
echo ""
echo "  🚀 正在启动考试系统..."
echo "  ═══════════════════════════════════════"
echo ""
echo "  浏览器将自动打开，如未打开请手动访问："
echo "  👉 http://localhost:8501"
echo ""
echo "  按 Ctrl+C 可以停止服务器。"
echo "  ═══════════════════════════════════════"
echo ""

# 延迟打开浏览器（等服务器启动后）
sleep 2 && open http://localhost:8501 &

# 启动 Streamlit
python3 -m streamlit run app.py --server.headless true

# 如果 streamlit 退出，暂停让用户看到错误信息
echo ""
echo "  考试系统已停止。按任意键关闭窗口..."
read -n 1
