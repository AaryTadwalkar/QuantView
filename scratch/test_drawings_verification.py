"""
Verification script for Task 2: Drawing Layer Pointer Events & Price Scale Isolation (Frontend).
Tests pointer-events behavior, empty space deselection, price scale isolation, and Escape handling.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9222
APP_URL = "http://127.0.0.1:8000"

def eval_js(ws, expr, await_promise=False):
    msg_id = int(time.time() * 1000) % 1000000
    req = {
        "id": msg_id,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": await_promise
        }
    }
    ws.send(json.dumps(req))
    while True:
        raw = ws.recv()
        data = json.loads(raw)
        if data.get("id") == msg_id:
            res = data.get("result", {})
            if "exceptionDetails" in res:
                raise RuntimeError(f"JS Exception: {res['exceptionDetails']}")
            return res.get("result", {}).get("value")

def main():
    user_data_dir = tempfile.mkdtemp(prefix="chrome_test_profile_")
    print(f"[*] Created temp Chrome user data dir: {user_data_dir}", flush=True)
    print(f"[*] Launching Headless Chrome pointing to {APP_URL}...", flush=True)

    chrome_cmd = [
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={user_data_dir}",
        "--disable-gpu",
        "--no-sandbox",
        "--window-size=1280,800",
        APP_URL
    ]
    proc = subprocess.Popen(chrome_cmd)

    ws = None
    try:
        # Wait for Chrome CDP port to open
        for attempt in range(25):
            try:
                resp = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=1)
                tabs = json.loads(resp.read().decode())
                page_tabs = [t for t in tabs if t.get("type") == "page"]
                if page_tabs:
                    ws_url = page_tabs[0]["webSocketDebuggerUrl"]
                    ws = websocket.create_connection(ws_url)
                    break
            except Exception:
                time.sleep(0.4)

        if not ws:
            print("[FAIL] Could not connect to Chrome DevTools Protocol!", flush=True)
            sys.exit(1)

        print("[*] Connected to Chrome DevTools Protocol via WebSocket.", flush=True)

        # Wait for QuantChart and DrawingLayer to initialize
        ready = False
        for attempt in range(40):
            ready = eval_js(ws, "Boolean((window.quantApp || window.app) && (window.quantApp || window.app).chart && (window.quantApp || window.app).chart.drawings && (window.quantApp || window.app).chart.drawings.canvas)")
            if ready:
                break
            time.sleep(0.5)

        if not ready:
            print("[FAIL] QuantView workstation did not initialize in time!", flush=True)
            sys.exit(1)

        print("[*] QuantView workstation initialized. Beginning verification tests...\n", flush=True)

        # Helper to get drawingLayer
        eval_js(ws, "window.getDL = () => (window.quantApp || window.app).chart.drawings;")

        # Test 1: In cursor mode, default pointerEvents is "none"
        res = eval_js(ws, """
        (() => {
            const dl = window.getDL();
            dl.setTool("cursor");
            return {
                tool: dl.tool,
                pointerEvents: dl.canvas.style.pointerEvents,
                cursor: dl.canvas.style.cursor,
                selected: dl.selected
            };
        })()
        """)
        assert res["tool"] == "cursor", f"Expected tool=cursor, got {res['tool']}"
        assert res["pointerEvents"] == "none", f"Expected pointerEvents=none, got {res['pointerEvents']}"
        assert res["cursor"] == "", f"Expected cursor='', got {res['cursor']}"
        assert res["selected"] is None, f"Expected selected=null, got {res['selected']}"
        print("  [PASS] Test 1: In cursor mode, pointerEvents='none', cursor='', selected=null", flush=True)

        # Test 2: In drawing mode (e.g. trend), pointerEvents="auto", cursor="crosshair"
        res = eval_js(ws, """
        (() => {
            const dl = window.getDL();
            dl.setTool("trend");
            return {
                tool: dl.tool,
                pointerEvents: dl.canvas.style.pointerEvents,
                cursor: dl.canvas.style.cursor
            };
        })()
        """)
        assert res["tool"] == "trend", f"Expected tool=trend, got {res['tool']}"
        assert res["pointerEvents"] == "auto", f"Expected pointerEvents=auto, got {res['pointerEvents']}"
        assert res["cursor"] == "crosshair", f"Expected cursor=crosshair, got {res['cursor']}"
        print("  [PASS] Test 2: In tool='trend' mode, pointerEvents='auto', cursor='crosshair'", flush=True)

        # Test 3: Switching back to cursor mode clears selection and resets pointerEvents to "none"
        res = eval_js(ws, """
        (() => {
            const dl = window.getDL();
            dl.selected = { id: 'dummy-selected' };
            dl.setTool("cursor");
            return {
                tool: dl.tool,
                pointerEvents: dl.canvas.style.pointerEvents,
                cursor: dl.canvas.style.cursor,
                selected: dl.selected
            };
        })()
        """)
        assert res["tool"] == "cursor", f"Expected tool=cursor, got {res['tool']}"
        assert res["pointerEvents"] == "none", f"Expected pointerEvents=none, got {res['pointerEvents']}"
        assert res["selected"] is None, f"Expected selected=null after setTool('cursor'), got {res['selected']}"
        print("  [PASS] Test 3: Switching to 'cursor' resets pointerEvents='none' and clears selected", flush=True)

        # Test 4: Hovering over drawing sets pointerEvents='auto'; moving to empty space sets pointerEvents='none' EVEN IF selected
        res = eval_js(ws, """
        (() => {
            const dl = window.getDL();
            dl.setTool("cursor");
            const w = dl.canvas.clientWidth || 800;
            const h = dl.canvas.clientHeight || 500;

            // Add a mock horizontal line at y = 200
            const mockLine = {
                id: "test-hline-1",
                type: "hline",
                points: [{ time: 1700000000, price: 24000 }]
            };
            dl.items = [mockLine];
            // Mock projection so y(24000) === 200 and x(1700000000) === 300
            dl.y = (p) => 200;
            dl.x = (t) => 300;
            dl.update();

            // 4a: Hovering directly over the line (x=300, y=200)
            const eventHover = new MouseEvent("mousemove", {
                clientX: dl.container.getBoundingClientRect().left + 300,
                clientY: dl.container.getBoundingClientRect().top + 200,
                bubbles: true
            });
            dl.container.dispatchEvent(eventHover);
            const peHover = dl.canvas.style.pointerEvents;
            const cursorHover = dl.canvas.style.cursor;

            // 4b: Line is selected
            dl.selected = mockLine;

            // 4c: Mouse moves to empty space (x=300, y=50) while drawing IS selected
            const eventEmpty = new MouseEvent("mousemove", {
                clientX: dl.container.getBoundingClientRect().left + 300,
                clientY: dl.container.getBoundingClientRect().top + 50,
                bubbles: true
            });
            dl.container.dispatchEvent(eventEmpty);
            const peEmptyWithSelected = dl.canvas.style.pointerEvents;

            return {
                peHover,
                cursorHover,
                peEmptyWithSelected,
                selectedStillPresent: Boolean(dl.selected)
            };
        })()
        """)
        assert res["peHover"] == "auto", f"Expected peHover=auto, got {res['peHover']}"
        assert res["cursorHover"] == "pointer", f"Expected cursorHover=pointer, got {res['cursorHover']}"
        assert res["peEmptyWithSelected"] == "none", f"Expected peEmptyWithSelected=none, got {res['peEmptyWithSelected']}"
        assert res["selectedStillPresent"] is True, "Selection was retained while pointerEvents released to chart"
        print("  [PASS] Test 4: Hovering over drawing sets pointerEvents='auto'. Moving off sets pointerEvents='none' even when selected!", flush=True)

        # Test 5: Clicking empty space immediately deselects and sets pointerEvents='none'
        res = eval_js(ws, """
        (() => {
            const dl = window.getDL();
            const mockLine = dl.items[0];
            dl.selected = mockLine;
            dl.canvas.style.pointerEvents = "auto";

            // Simulate click on empty space (x=300, y=50)
            const rect = dl.canvas.getBoundingClientRect();
            const clickEmpty = new MouseEvent("click", {
                clientX: rect.left + 300,
                clientY: rect.top + 50,
                bubbles: true
            });
            dl.canvas.dispatchEvent(clickEmpty);

            return {
                selected: dl.selected,
                pointerEvents: dl.canvas.style.pointerEvents
            };
        })()
        """)
        assert res["selected"] is None, f"Expected selected=null on empty click, got {res['selected']}"
        assert res["pointerEvents"] == "none", f"Expected pointerEvents=none on empty click, got {res['pointerEvents']}"
        print("  [PASS] Test 5: Clicking empty space immediately deselects (selected=null) and sets pointerEvents='none'", flush=True)

        # Test 6: In cursor mode, pointer over right 65px price scale column (x >= plotWidth) NEVER hits drawings
        res = eval_js(ws, """
        (() => {
            const dl = window.getDL();
            const w = dl.canvas.clientWidth || 800;
            const plotWidth = w - 65;

            // Test hitTest in the price scale column (e.g. plotWidth + 20)
            const hitInScale = dl.hitTest(plotWidth + 20, 200);

            // Dispatch mousemove inside price scale
            const rect = dl.container.getBoundingClientRect();
            const eventScale = new MouseEvent("mousemove", {
                clientX: rect.left + plotWidth + 20,
                clientY: rect.top + 200,
                bubbles: true
            });
            dl.container.dispatchEvent(eventScale);

            return {
                hitInScale,
                pointerEvents: dl.canvas.style.pointerEvents
            };
        })()
        """)
        assert res["hitInScale"] is None, f"Expected hitInScale=null in price scale, got {res['hitInScale']}"
        assert res["pointerEvents"] == "none", f"Expected pointerEvents=none in price scale, got {res['pointerEvents']}"
        print("  [PASS] Test 6: Price scale column (x >= plotWidth) is isolated: hitTest returns null, pointerEvents stays 'none'", flush=True)

        # Test 7: Price scale isolation in drawOne for hline and hray (strictly clipped at plotWidth)
        res = eval_js(ws, """
        (() => {
            const dl = window.getDL();
            const w = 800;
            const h = 500;
            const plotWidth = w - 65; // 735

            // Create an offscreen test canvas
            const testCanvas = document.createElement("canvas");
            testCanvas.width = w;
            testCanvas.height = h;
            const testCtx = testCanvas.getContext("2d");

            // Draw hline
            const hline = { type: "hline", points: [{ time: 1000, price: 24000 }], color: "#ff0000" };
            dl.y = () => 150;
            dl.drawOne(testCtx, { width: w, height: h }, hline, false);

            // Draw hray
            const hray = { type: "hray", points: [{ time: 1000, price: 24000 }], color: "#00ff00" };
            dl.drawOne(testCtx, { width: w, height: h }, hray, false);

            // Sample pixels inside the price scale column (from plotWidth + 1 to w - 1)
            const imgData = testCtx.getImageData(plotWidth + 1, 0, 64, h).data;
            let paintedPixels = 0;
            for (let i = 3; i < imgData.length; i += 4) {
                if (imgData[i] > 0) {
                    paintedPixels++;
                }
            }

            return {
                plotWidth,
                paintedPixelsInPriceScale: paintedPixels
            };
        })()
        """)
        assert res["paintedPixelsInPriceScale"] == 0, f"Expected 0 pixels painted in price scale, got {res['paintedPixelsInPriceScale']}"
        print(f"  [PASS] Test 7: drawOne strictly clips hline & hray at plotWidth ({res['plotWidth']}px): 0 painted pixels in price scale!", flush=True)

        # Test 8: Escape key triggers cancel(), setting pointerEvents='none' and selected=null
        res = eval_js(ws, """
        (() => {
            const dl = window.getDL();
            dl.selected = dl.items[0];
            dl.canvas.style.pointerEvents = "auto";

            // Dispatch Escape key event
            window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));

            return {
                selected: dl.selected,
                pointerEvents: dl.canvas.style.pointerEvents,
                tool: dl.tool
            };
        })()
        """)
        assert res["selected"] is None, f"Expected selected=null on Escape, got {res['selected']}"
        assert res["pointerEvents"] == "none", f"Expected pointerEvents=none on Escape, got {res['pointerEvents']}"
        assert res["tool"] == "cursor", f"Expected tool=cursor on Escape, got {res['tool']}"
        print("  [PASS] Test 8: Escape key cleanly cancels selection and sets pointerEvents='none'", flush=True)

        # Test 9: onPointerDown in cursor mode: hitting drawing sets pointerEvents='auto'; clicking empty space deselects & sets pointerEvents='none'
        res = eval_js(ws, """
        (() => {
            const dl = window.getDL();
            dl.setTool("cursor");
            const rect = dl.canvas.getBoundingClientRect();

            // 9a: Pointer down on drawing at (300, 150) (matching dl.y=150)
            const downOnDrawing = new PointerEvent("pointerdown", {
                clientX: rect.left + 300,
                clientY: rect.top + 150,
                pointerId: 1,
                bubbles: true
            });
            dl.canvas.dispatchEvent(downOnDrawing);
            const selectedAfterHit = dl.selected;
            const peAfterHit = dl.canvas.style.pointerEvents;

            // 9b: Pointer down on empty space at (300, 50)
            const downOnEmpty = new PointerEvent("pointerdown", {
                clientX: rect.left + 300,
                clientY: rect.top + 50,
                pointerId: 1,
                bubbles: true
            });
            dl.canvas.dispatchEvent(downOnEmpty);
            const selectedAfterEmpty = dl.selected;
            const peAfterEmpty = dl.canvas.style.pointerEvents;

            return {
                hasSelectedAfterHit: Boolean(selectedAfterHit),
                peAfterHit,
                selectedAfterEmpty,
                peAfterEmpty
            };
        })()
        """)
        assert res["hasSelectedAfterHit"] is True, "Expected drawing selected after clicking it"
        assert res["peAfterHit"] == "auto", f"Expected pointerEvents='auto' after clicking drawing, got {res['peAfterHit']}"
        assert res["selectedAfterEmpty"] is None, f"Expected selected=null after clicking empty space, got {res['selectedAfterEmpty']}"
        assert res["peAfterEmpty"] == "none", f"Expected pointerEvents='none' after clicking empty space, got {res['peAfterEmpty']}"
        print("  [PASS] Test 9: onPointerDown in cursor mode handles drawing selection & empty space deselection correctly", flush=True)

        print("\n=======================================================", flush=True)
        print(">>> ALL 9 DRAWING VERIFICATION TESTS PASSED SUCCESFULLY! <<<", flush=True)
        print("=======================================================", flush=True)

    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        try:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass

if __name__ == "__main__":
    main()
