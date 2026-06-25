@echo off
chcp 65001 >nul
title Python 在线考试系统

REM ==========================================
REM  🐍 Python 在线考试系统 — 一键启动脚本
REM  适用平台：Windows
REM  用法：双击此文件即可启动
REM ==========================================

REM 切换到脚本所在目录
cd /d "%~dp0"

echo.
echo   ╔══════════════════════════════════════╗
echo   ║   🐍 Python 在线考试系统            ║
echo   ║   正在检查运行环境...               ║
echo   ╚══════════════════════════════════════╝
echo.

REM ---- 1. 检查 Python ----
echo   🔍 检查 Python...
python --version >nul 2>&1
if %errorlevel%==0 (
    echo   ✅ 已找到 Python
) else (
    python3 --version >nul 2>&1
    if %errorlevel%==0 (
        echo   ✅ 已找到 Python3
        set PYTHON_CMD=python3
    ) else (
        echo   ❌ 未找到 Python，请先安装 Python3。
        echo   📥 下载地址：https://www.python.org/downloads/
        echo.
        echo   安装时请勾选 "Add Python to PATH"
        echo.
        pause
        exit /b 1
    )
)

REM 确定 Python 命令
if not defined PYTHON_CMD (
    python --version >nul 2>&1
    if %errorlevel%==0 (set PYTHON_CMD=python) else (set PYTHON_CMD=python3)
)

REM ---- 2. 检查 / 安装 streamlit ----
echo   🔍 检查 streamlit 是否已安装...
%PYTHON_CMD% -c "import streamlit" >nul 2>&1
if %errorlevel%==0 (
    echo   ✅ streamlit 已安装
) else (
    echo   📥 正在安装 streamlit（首次使用需要几分钟，请耐心等待）...
    %PYTHON_CMD% -m pip install streamlit --quiet
    if %errorlevel%==0 (
        echo   ✅ streamlit 安装成功！
    ) else (
        echo   ❌ streamlit 安装失败，请检查网络连接后重试。
        echo.
        pause
        exit /b 1
    )
)

REM ---- 3. 启动考试系统 ----
echo.
echo   🚀 正在启动考试系统...
echo   ═══════════════════════════════════════
echo.
echo   浏览器将自动打开，如未打开请手动访问：
echo   👉 http://localhost:8501
echo.
echo   按 Ctrl+C 可以停止服务器。
echo   ═══════════════════════════════════════
echo.

REM 启动浏览器
start http://localhost:8501

REM 启动 Streamlit
%PYTHON_CMD% -m streamlit run app.py --server.headless true

echo.
echo   考试系统已停止。按任意键关闭窗口...
pause
