@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
%PY% --version >nul 2>nul || (echo Python غير مثبت. نزّله من python.org وفعّل خيار Add Python to PATH أثناء التثبيت. & pause & exit /b)
echo تثبيت المتطلبات (مرة واحدة)...
%PY% -m pip install -r requirements.txt --quiet --disable-pip-version-check
start "" http://localhost:8080
%PY% app.py
pause
