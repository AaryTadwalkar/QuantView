venv activate command:
(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& c:\Algo\quantview\venv\Scripts\Activate.ps1)


WS command:
python tools/ops/run_collector_ws.py --atm-count 5
snapshot command:
python tools/ops/run_collector_snapshot.py --loop --interval-sec 60

web app
cd C:\Algo\quantview
.\venv\Scripts\python.exe -m uvicorn services.api.main:app --port 8000 --host 127.0.0.1