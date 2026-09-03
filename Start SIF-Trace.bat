@echo off
setlocal enabledelayedexpansion
title SIF-Trace

cd /d "%~dp0"

echo.
echo   ===================================================================
echo     SIF-Trace  ^|  SIF Precursor Detection Engine
echo     AI prioritises. HSE decides.
echo   ===================================================================
echo.

set PY=.venv\Scripts\python.exe

REM ---------------------------------------------------------------- checks
if not exist "%PY%" (
    echo   [X] Python environment not found at .venv
    echo.
    echo       Run this once to create it:
    echo         python -m venv .venv
    echo         .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "data\sif_reports.csv" (
    echo   [X] Demo corpus missing: data\sif_reports.csv
    echo.
    pause
    exit /b 1
)

if not exist "frontend\dist\index.html" (
    echo   [!] Frontend not built. Building now, this takes about 30 seconds...
    pushd frontend
    call npm run build
    popd
    if not exist "frontend\dist\index.html" (
        echo   [X] Build failed. Run "npm install" inside the frontend folder first.
        pause
        exit /b 1
    )
)

REM ------------------------------------------------------- free the port
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:"LISTENING" ^| findstr ":8000 "') do (
    echo   [i] Port 8000 was in use - stopping old instance ^(pid %%p^)
    taskkill /f /pid %%p >nul 2>&1
)

echo   [+] Starting SIF-Trace...
echo.

start "" /b "%PY%" -m uvicorn main:app --host 127.0.0.1 --port 8000 --app-dir backend

REM ------------------------------------------------------- wait for ready
set READY=0
for /l %%i in (1,1,60) do (
    if !READY!==0 (
        timeout /t 1 /nobreak >nul
        curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/api/health > "%TEMP%\sif_rc.txt" 2>nul
        set /p RC=<"%TEMP%\sif_rc.txt"
        if "!RC!"=="200" set READY=1
    )
)
del "%TEMP%\sif_rc.txt" >nul 2>&1

if !READY!==0 (
    echo   [X] Server did not start. Try running it manually:
    echo         cd backend
    echo         ..\.venv\Scripts\python.exe -m uvicorn main:app --port 8000
    echo.
    pause
    exit /b 1
)

echo   [OK] SIF-Trace is running
echo.
echo        Dashboard :  http://localhost:8000
echo        API docs  :  http://localhost:8000/docs
echo.
echo        DEMO DATA - NOT ACTUAL OIL RECORDS
echo.
echo   ===================================================================
echo     Opening your browser. Close this window to stop the server.
echo   ===================================================================
echo.

start "" http://localhost:8000

REM Keep the window alive; closing it stops the server.
pause >nul
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:"LISTENING" ^| findstr ":8000 "') do taskkill /f /pid %%p >nul 2>&1
endlocal
