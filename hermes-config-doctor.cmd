@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "SCRIPT=%~dp0hermes_config_doctor.py"
if not exist "%SCRIPT%" goto NOFILE
where py >nul 2>nul
if errorlevel 1 goto TRY_PYTHON
py -3 -c "import yaml" >nul 2>nul
if errorlevel 1 goto TRY_PYTHON
py -3 "%SCRIPT%" %*
set "RC=%errorlevel%"
goto TAIL
:TRY_PYTHON
where python >nul 2>nul
if errorlevel 1 goto NO_PY
python -c "import yaml" >nul 2>nul
if errorlevel 1 goto NO_YAML
python "%SCRIPT%" %*
set "RC=%errorlevel%"
goto TAIL
:NOFILE
echo [ERROR] hermes_config_doctor.py not found next to this launcher.
set "RC=1"
goto TAIL
:NO_PY
echo [ERROR] Python not found on PATH. Install Python 3.8+ and tick "Add python.exe to PATH".
set "RC=1"
goto TAIL
:NO_YAML
echo [ERROR] PyYAML missing. Run: python -m pip install pyyaml
set "RC=1"
goto TAIL
:TAIL
if "%~1"=="" pause
endlocal & exit /b %RC%
