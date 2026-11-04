@echo off
rem Harvest Moon: Animal Parade - build (first time) and play.
rem Put your disc image in the "assets" folder first (see assets\README.md).
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% hmap.py play %*
if errorlevel 1 (
    echo.
    echo Something went wrong. The messages above say what; "py hmap.py doctor" checks your setup.
    pause
)
