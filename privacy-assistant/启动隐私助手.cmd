@echo off
start "" "%~dp0runtime\pythonw.exe" -I -B "%~dp0scripts\auto_setup.py" --agent workbuddy
