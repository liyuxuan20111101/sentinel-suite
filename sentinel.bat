@echo off
rem sentinel-suite 一键入口（Windows）
rem   双击本文件        → 交互菜单
rem   sentinel.bat demo → 一分钟演示
rem   sentinel.bat web  → 启动 Web 控制台
python "%~dp0sentinel.py" %*
if "%~1"=="" pause
