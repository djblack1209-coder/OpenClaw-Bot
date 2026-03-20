@echo off
chcp 65001 >nul
echo.
echo  ========================================
echo       OpenClaw 一键部署器
echo  ========================================
echo.
echo  正在准备环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] 未检测到 Python
    echo  请先安装 Python 3.8+
    echo  下载: https://www.python.org/downloads/
    echo  安装时务必勾选 "Add to PATH"
    echo.
    pause
    exit /b 1
)
pip install -q flask 2>nul
echo  启动中，浏览器将自动打开...
python web_installer.py
pause
