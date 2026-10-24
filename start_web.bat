@echo off
rem 双击即可启动 Web 控制台（自动打开浏览器，只绑定本机 127.0.0.1）
cd /d "%~dp0"
python sentinel.py web
pause
