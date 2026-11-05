@echo off
chcp 65001 >nul
rem hermes-config-doctor launcher - any Windows with Python 3.8+ installed
setlocal
set "SCRIPT=%~dp0hermes_config_doctor.py"
if not exist "%SCRIPT%" (
  echo [ERROR] hermes_config_doctor.py not found next to this launcher
  exit /b 1
)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT%" %*
  exit /b %errorlevel%
)
where python >nul 2>nul
if %errorlevel%==0 (
  python "%SCRIPT%" %*
  exit /b %errorlevel%
)
echo [ERROR] Python not found. Install Python 3.8+ and tick Add python.exe to PATH.
exit /b 1
