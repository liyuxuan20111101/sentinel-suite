@echo off
rem sentinel-suite 一键入口（Windows）：双击不能带参数，请在命令行用
rem   sentinel.bat demo        一分钟演示
rem   sentinel.bat web         启动本地 Web 控制台
python "%~dp0sentinel.py" %*
