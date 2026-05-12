@echo off
cd /d "%~dp0"
python run.py play
if errorlevel 1 pause
