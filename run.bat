@echo off
echo ============================================
echo   FDA Warning Letter Analysis Dashboard
echo ============================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

REM Check if dependencies are installed
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
    echo.
)

REM Check if data exists
if not exist "data\warning_letters.csv" (
    echo No data found. Fetching FDA warning letters...
    echo This may take 30-60 minutes for the first run.
    echo.
    python fetch_fda_data.py --limit 50
    echo.
    echo Generating summaries...
    python summarize_letters.py
    echo.
)

echo Starting dashboard at http://localhost:8501
echo Press Ctrl+C to stop.
echo.
python -m streamlit run dashboard.py --server.port 8501
pause
