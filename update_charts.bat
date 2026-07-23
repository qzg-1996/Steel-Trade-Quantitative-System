@echo off
cd /d %~dp0
echo Updating data and generating charts ...
python main.py
pause
