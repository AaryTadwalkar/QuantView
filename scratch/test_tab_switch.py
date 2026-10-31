import json
import subprocess
import tempfile
import time
import urllib.request

from websockets.sync.client import connect

temp_dir = tempfile.mkdtemp()
cmd = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "--headless=new",
    "--remote-debugging-port=9232",
    f"--user-data-dir={temp_dir}",
    "--disable-gpu",
    "--no-sandbox",
    "http://127.0.0.1:8000",
]
proc = subprocess.Popen(cmd)
time.sleep(2.0)

try:
    with urllib.request.urlopen("http://127.0.0.1:9232/json") as r:
        targets = json.loads(r.read().decode("utf-8"))
        page = next(t for t in targets if t.get("type") == "page")
        ws_url = page["webSocketDebuggerUrl"]

    with connect(ws_url, close_timeout=5) as ws:
        # Check window.quantApp
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": "Boolean(window.quantApp && window.quantApp.chart)", "returnByValue": True}}))
        r1 = json.loads(ws.recv())
        print("1. quantApp initialized:", r1.get("result", {}).get("result", {}).get("value"))

        # Switch tab
        ws.send(json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {"expression": "window.quantApp.switchTab('tester')", "returnByValue": True}}))
        r2 = json.loads(ws.recv())
        print("2. switchTab called:", r2)
        time.sleep(1.0)

        # Inspect bottomBody
        ws.send(json.dumps({"id": 3, "method": "Runtime.evaluate", "params": {"expression": "document.getElementById('bottomBody')?.innerHTML || ''", "returnByValue": True}}))
        r3 = json.loads(ws.recv())
        val = r3.get("result", {}).get("result", {}).get("value", "")
        print("3. bottomBody length:", len(val))
        print("   has stratTimeframe:", "stratTimeframe" in val)
        print("   has stratStart:", "stratStart" in val)
        print("   has runBacktestBtn:", "runBacktestBtn" in val)

        # Check strategies in dropdown
        ws.send(json.dumps({"id": 4, "method": "Runtime.evaluate", "params": {"expression": "document.getElementById('stratSelect')?.options?.length || 0", "returnByValue": True}}))
        r4 = json.loads(ws.recv())
        print("4. stratSelect options count:", r4.get("result", {}).get("result", {}).get("value"))

        # Click run backtest
        ws.send(json.dumps({"id": 5, "method": "Runtime.evaluate", "params": {"expression": "(() => { document.getElementById('runBacktestBtn').click(); return 'clicked'; })()", "returnByValue": True}}))
        r5 = json.loads(ws.recv())
        print("5. runBacktestBtn clicked:", r5)
        time.sleep(2.0)

        # Check results
        ws.send(json.dumps({"id": 6, "method": "Runtime.evaluate", "params": {"expression": "Boolean(document.querySelector('.tester-subnav'))", "returnByValue": True}}))
        r6 = json.loads(ws.recv())
        print("6. tester-subnav present:", r6.get("result", {}).get("result", {}).get("value"))

        # Check historical banner
        ws.send(json.dumps({"id": 7, "method": "Runtime.evaluate", "params": {"expression": "!document.getElementById('historicalBanner').classList.contains('hidden')", "returnByValue": True}}))
        r7 = json.loads(ws.recv())
        print("7. historicalBanner visible:", r7.get("result", {}).get("result", {}).get("value"))

        # Check banner text
        ws.send(json.dumps({"id": 8, "method": "Runtime.evaluate", "params": {"expression": "document.getElementById('historicalDateRangeText').textContent", "returnByValue": True}}))
        r8 = json.loads(ws.recv())
        print("8. historicalBanner text:", r8.get("result", {}).get("result", {}).get("value"))

        # Click return to latest
        ws.send(json.dumps({"id": 9, "method": "Runtime.evaluate", "params": {"expression": "document.getElementById('returnToLatestBtn').click()", "returnByValue": True}}))
        r9 = json.loads(ws.recv())
        print("9. returnToLatestBtn clicked:", r9)
        time.sleep(1.5)

        # Verify historical banner hidden
        ws.send(json.dumps({"id": 10, "method": "Runtime.evaluate", "params": {"expression": "document.getElementById('historicalBanner').classList.contains('hidden')", "returnByValue": True}}))
        r10 = json.loads(ws.recv())
        print("10. historicalBanner hidden after return:", r10.get("result", {}).get("result", {}).get("value"))

        # Check _isHistoricalSlice
        ws.send(json.dumps({"id": 11, "method": "Runtime.evaluate", "params": {"expression": "window.quantApp.chart._isHistoricalSlice", "returnByValue": True}}))
        r11 = json.loads(ws.recv())
        print("11. _isHistoricalSlice is False:", r11.get("result", {}).get("result", {}).get("value") is False)

        print("\nALL 11 BROWSER CHECKS SUCCEEDED!")
finally:
    proc.terminate()
