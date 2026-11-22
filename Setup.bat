@echo off
setlocal EnableExtensions
title Study Timer - Setup
cd /d "%~dp0"
echo.
echo === Study Timer setup ===
echo.

echo [1/2] Checking for Python...
call :find
if defined PYDIR (
    echo   Python is already installed - skipping install.
    goto :app
)
echo   Python not found. Installing it now, please wait...
call :install
call :find
if not defined PYDIR (
    echo.
    echo   ERROR: Python could not be installed automatically.
    echo   Check your internet connection and run Setup.bat again,
    echo   or install Python manually from https://www.python.org/downloads/
    echo   ^(tick "Add python.exe to PATH"^).
    echo.
    pause
    exit /b 1
)
echo   Python installed.

:app
echo.
echo [2/2] Setting up the app...
set "APPFILE="
for %%F in (*.pyw) do if not defined APPFILE set "APPFILE=%%F"
if not defined APPFILE (
    echo   No .pyw file next to Setup.bat, so only Python was set up.
    echo   Put your .pyw file in this folder and run Setup.bat again to add a shortcut.
    echo.
    pause
    exit /b 0
)
set "APPDIR=%LOCALAPPDATA%\StudyTimerX"
if not exist "%APPDIR%" mkdir "%APPDIR%"
copy /y "%APPFILE%" "%APPDIR%\" >nul
copy /y "*.ttf" "%APPDIR%\" >nul 2>&1
set "TARGET=%APPDIR%\%APPFILE%"
set "PYW_EXE=%PYDIR%pythonw.exe"
powershell -NoProfile -Command "$q=[char]34; $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Study Timer.lnk')); $s.TargetPath=$env:PYW_EXE; $s.Arguments=$q+$env:TARGET+$q; $s.WorkingDirectory=$env:APPDIR; $s.IconLocation=$env:PYW_EXE+',0'; $s.Save()"
echo   Desktop shortcut "Study Timer" created.
echo.
echo Done! Starting Study Timer...
start "" "%PYW_EXE%" "%TARGET%"
timeout /t 3 >nul
exit /b 0


:: ---------- find a real Python 3.8+ with tkinter; sets PYDIR (with trailing backslash) ----------
:find
set "PYDIR="
for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do if not defined PYDIR call :check "%%~dpP"
if defined PYDIR exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if not defined PYDIR call :check "%%~fD\"
for /d %%D in ("%ProgramFiles%\Python3*") do if not defined PYDIR call :check "%%~fD\"
exit /b 0

:check
if not exist "%~1pythonw.exe" exit /b 0
"%~1python.exe" -c "import sys,tkinter; sys.exit(0 if sys.version_info>=(3,8) else 1)" >nul 2>&1
if not errorlevel 1 set "PYDIR=%~1"
exit /b 0


:: ---------- install Python for the current user (no admin needed) ----------
:install
where winget >nul 2>&1
if not errorlevel 1 (
    echo   Using winget...
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    call :find
    if defined PYDIR exit /b 0
    echo   winget did not finish, downloading from python.org instead...
)
set "ARCH=-amd64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=-arm64"
if /i "%PROCESSOR_ARCHITECTURE%"=="x86" if not defined PROCESSOR_ARCHITEW6432 set "ARCH="
set "URL=https://www.python.org/ftp/python/3.12.10/python-3.12.10%ARCH%.exe"
set "EXE=%TEMP%\python-installer.exe"
echo   Downloading %URL%
curl.exe -L --fail -s -o "%EXE%" "%URL%" || powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -UseBasicParsing '%URL%' -OutFile '%EXE%'"
if not exist "%EXE%" exit /b 1
echo   Running the Python installer...
"%EXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0 Include_tcltk=1 Shortcuts=0
del "%EXE%" >nul 2>&1
exit /b 0
