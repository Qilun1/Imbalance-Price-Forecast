@echo off
rem Starts the forecast API and the dashboard, then opens the browser.
rem
rem   start-dashboard.cmd         real data if the stores exist (static_data\static.duckdb and
rem                               backend\infer_data\forecasts.duckdb), otherwise invented mock data
rem   start-dashboard.cmd real    the pipeline's forecasts (build them first: root README, "Reproduce the submission")
rem   start-dashboard.cmd mock    invented mock data, needs no licensed files
rem
rem The API gets its own window. Close both windows to stop everything.

setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo The Python environment is missing. Run "uv sync" in this folder first.
  exit /b 1
)

if not exist frontend\node_modules (
  echo Installing the dashboard's packages...
  pushd frontend
  call npm install
  popd
)

set IMBALANCE_DATA_MODE=mock
if exist static_data\static.duckdb if exist backend\infer_data\forecasts.duckdb set IMBALANCE_DATA_MODE=real
if /i "%~1"=="real" set IMBALANCE_DATA_MODE=real
if /i "%~1"=="mock" set IMBALANCE_DATA_MODE=mock
echo Data: %IMBALANCE_DATA_MODE%

start "Imbalance API, %IMBALANCE_DATA_MODE% data" cmd /k .venv\Scripts\python.exe -m uvicorn backend.api.main:app --port 8000 --log-level warning

echo Waiting for the API...
for /l %%i in (1,1,60) do (
  curl -fs -o nul -m 2 http://127.0.0.1:8000/api/meta && goto api_ready
  ping -n 2 127.0.0.1 >nul
)
echo The API did not start. Read the message in its window.
exit /b 1

:api_ready
echo API ready. Starting the dashboard at http://localhost:3000
start "" /min cmd /c "ping -n 6 127.0.0.1 >nul & start "" http://localhost:3000"
cd frontend
call npm run dev
