import asyncio
import json
import subprocess
import time
import urllib.request

import websockets


async def check():
    chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    proc = subprocess.Popen([chrome_path, '--headless=new', '--remote-debugging-port=9222', '--disable-gpu', '--no-sandbox', 'http://localhost:8000'])
    time.sleep(2.0)
    try:
        with urllib.request.urlopen('http://127.0.0.1:9222/json') as response:
            targets = json.loads(response.read().decode())
        ws_url = next(t for t in targets if t.get('type') == 'page')['webSocketDebuggerUrl']
        async with websockets.connect(ws_url) as ws:
            msg_id = 10
            async def send_cmd(method, params=None):
                nonlocal msg_id
                msg_id += 1
                await ws.send(json.dumps({'id': msg_id, 'method': method, 'params': params or {}}))
                while True:
                    res = json.loads(await ws.recv())
                    if res.get('id') == msg_id:
                        return res.get('result', {})

            await send_cmd('Runtime.enable')
            await send_cmd('Console.enable')

            async def evaluate(expr):
                r = await send_cmd('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': True})
                return r.get('result', {}).get('value')

            await evaluate('window.quantApp.switchTab("tester")')
            await asyncio.sleep(0.5)

            # Check form values
            form_values = await evaluate('''
                (() => {
                    return {
                        startDate: document.getElementById('testerStartDate')?.value,
                        endDate: document.getElementById('testerEndDate')?.value,
                        strat: document.getElementById('testerStrategy')?.value,
                        mode: document.getElementById('testerMode')?.value
                    };
                })()
            ''')
            print('Form values:', form_values)

            # Trigger backtest
            click_res = await evaluate('''
                (async () => {
                    const btn = document.getElementById("runBacktestBtn");
                    if (!btn) return "No button";
                    btn.click();
                    return "Clicked";
                })()
            ''')
            print('Click status:', click_res)

            # Wait for response
            for _ in range(10):
                await asyncio.sleep(0.5)
                status = await evaluate('''
                    (() => {
                        const table = document.getElementById("testerTradeLogTable");
                        const tbody = table ? table.querySelector("tbody") : null;
                        const rows = tbody ? tbody.querySelectorAll("tr").length : 0;
                        const btn = document.getElementById("runBacktestBtn");
                        const toast = document.querySelector(".toast")?.textContent;
                        const runs = window.quantApp.lastBacktestResult;
                        return {
                            btnText: btn?.textContent,
                            btnDisabled: btn?.disabled,
                            rows,
                            toast,
                            hasLastResult: runs != null,
                            tradesCount: runs?.trades?.length,
                            roundTrips: runs?.metrics?.round_trips
                        };
                    })()
                ''')
                print('Status:', status)
                if status.get('hasLastResult'):
                    break

            # Let's inspect the trades array and table rendering
            details = await evaluate('''
                (() => {
                    const table = document.getElementById("testerTradeLogTable");
                    const tbody = table ? table.querySelector("tbody") : null;
                    const rows = tbody ? Array.from(tbody.querySelectorAll("tr")).map(r => r.innerText.replace(/\\n/g, " | ")) : [];
                    return {
                        rows,
                        tableHTML: table?.parentElement?.innerHTML?.slice(0, 500)
                    };
                })()
            ''')
            print('Trade table details:', json.dumps(details, indent=2))
    finally:
        proc.terminate()

asyncio.run(check())

