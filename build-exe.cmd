@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ================================================
echo   MAA 远程控制 - 打包 Windows 单文件 exe
echo ================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有找到 python 命令，请先安装 Python 3.11+ 并勾选 "Add to PATH"。
    pause
    exit /b 1
)

echo [1/2] 安装打包依赖……
python -m pip install -q -r requirements-build.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络或 pip 配置。
    pause
    exit /b 1
)

echo [2/2] 开始打包……
python tools\build_exe.py %*
if errorlevel 1 (
    echo [错误] 打包失败，请看上面的日志。
    pause
    exit /b 1
)

echo.
echo 完成！双击 dist\maa-remote-control.exe 即可运行。
pause
exit /b 0
