@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install pandas --quiet
python merge_data.py
echo.
pause
