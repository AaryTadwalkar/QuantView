/**
 * 1. What this file does:
 *    Interactive chart drawing tools, transparent canvas overlay, geometric hit-testing,
 *    and REST persistence engine for QuantView (apps/web/js/drawings.js).
 *    Supports 13 technical drawing tools (Trendline, Ray, Extended Line, Horizontal Line,
 *    Horizontal Ray, Vertical Line, Parallel Channel, Rectangle, Fibonacci Retracement,
 *    Price Measure/Ruler, Long Position, Short Position, and Text Note), manages interactive
 *    mouse and pointer events, synchronizes canvas resolution with chart dimensions, and
 *    implements the verified hit-test bounding box bug fix for Long and Short position boxes
 *    (Milestone M6-13, Gate G4).
 *
 * 2. Overall design:
 *    - Implements DrawingLayer as both a transparent DOM canvas overlay and a Lightweight Charts
 *      v5 series primitive (ISeriesPrimitive) attached to the primary candlestick series.
 *    - Points are stored canonically as { time: UtcEpochSec, price: number }, ensuring drawings
 *      remain invariant and anchored during timeframe switching or interval changes.
 *    - Corrects the Long/Short hitTest calculation so that clicking anywhere in the entry,
 *      stop-loss, or target zones selects the position box instantly for deletion or editing.
 *    - Automatically synchronizes drawing entities with the backend FastAPI persistence endpoints:
 *        * POST /api/v1/charts/drawings (upsert)
 *        * GET /api/v1/charts/drawings?symbol=... (load)
 *        * DELETE /api/v1/charts/drawings/{id} (single delete)
 *        * DELETE /api/v1/charts/drawings?symbol=... (bulk purge)
 *
 * 3. Elements in the file:
 *    - TOOLS: Array of 14 drawing tool descriptors (cursor + 13 drawing tools) with icons and point counts.
 *    - TOOL_BY_ID: Map of tool configuration objects keyed by tool identifier.
 *    - FIB_LEVELS: Array of standard Fibonacci retracement ratios (0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.618).
 *    - COLORS: Canonical color tokens for lines, Fibonacci levels, long/profit, and short/loss.
 *    - DrawingLayer: Main controller class managing overlay canvas, event listeners, drawing primitives,
 *      hit-testing, and backend REST synchronization.
 *
 * 4. Final output of the file:
 *    - Exported TOOLS, TOOL_BY_ID, FIB_LEVELS, COLORS, and DrawingLayer class.
 */

import { api, fmtPrice } from "./api.js";

export const TOOLS = [
  { id: "cursor", label: "Cursor / Select", points: 0, icon: '<path d="M5 3l14 7-6 2-2 6z"/>' },
  {
    id: "trend",
    label: "Trend line",
    points: 2,
    icon: '<path d="M4 19L20 5"/><circle cx="4" cy="19" r="1.6"/><circle cx="20" cy="5" r="1.6"/>',
  },
  {
    id: "ray",
    label: "Ray",
    points: 2,
    icon: '<path d="M4 19L21 4"/><circle cx="4" cy="19" r="1.6"/><circle cx="11" cy="13" r="1.6"/>',
  },
  {
    id: "extended",
    label: "Extended line",
    points: 2,
    icon: '<path d="M2 21L22 3"/><circle cx="8" cy="16" r="1.6"/><circle cx="16" cy="9" r="1.6"/>',
  },
  {
    id: "hline",
    label: "Horizontal line",
    points: 1,
    icon: '<path d="M3 12h18"/><circle cx="12" cy="12" r="1.6"/>',
  },
  {
    id: "hray",
    label: "Horizontal ray",
    points: 1,
    icon: '<path d="M8 12h13"/><circle cx="8" cy="12" r="1.6"/>',
  },
  {
    id: "vline",
    label: "Vertical line",
    points: 1,
    icon: '<path d="M12 3v18"/><circle cx="12" cy="12" r="1.6"/>',
  },
  {
    id: "channel",
    label: "Parallel channel",
    points: 3,
    icon: '<path d="M3 15L15 5M9 21l12-10"/>',
  },
  {
    id: "rect",
    label: "Rectangle",
    points: 2,
    icon: '<rect x="4" y="6" width="16" height="12" rx="1"/>',
  },
  {
    id: "fib",
    label: "Fib retracement",
    points: 2,
    icon: '<path d="M3 5h18M3 10h18M3 14h18M3 19h18" stroke-dasharray="2 2"/>',
  },
  {
    id: "measure",
    label: "Price range / measure",
    points: 2,
    icon: '<path d="M12 3v18M8 7l4-4 4 4M8 17l4 4 4-4"/>',
  },
  {
    id: "long",
    label: "Long position",
    points: 2,
    icon: '<rect x="4" y="5" width="16" height="7" fill="currentColor" fill-opacity=".25"/><rect x="4" y="12" width="16" height="7"/>',
  },
  {
    id: "short",
    label: "Short position",
    points: 2,
    icon: '<rect x="4" y="5" width="16" height="7"/><rect x="4" y="12" width="16" height="7" fill="currentColor" fill-opacity=".25"/>',
  },
  {
    id: "text",
    label: "Text note",
    points: 1,
    icon: '<path d="M5 6h14M12 6v13"/>',
  },
];

export const TOOL_BY_ID = Object.fromEntries(TOOLS.map((t) => [t.id, t]));
export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.618];

export const COLORS = {
  line: "#2962ff",
  fib: "#787b86",
  up: "rgba(8,153,129,",
  down: "rgba(242,54,69,",
};

/**
 * 1. The use of class:
 *    Manages the chart drawing overlay canvas, user interactions, geometric hit-testing,
 *    and REST synchronization with the FastAPI drawings storage backend.
 *
 * 2. What the class contains:
 *    - chart: Reference to the parent QuantChart instance.
 *    - items: Array of persisted drawing objects for the active symbol.
 *    - temp: In-progress temporary drawing object currently being constructed by the user.
 *    - selected: Currently selected drawing item highlighted on canvas.
 *    - tool: Currently active drawing tool identifier (default: "cursor").
 *    - canvas: HTML5 transparent overlay canvas mounted on top of the chart container.
 *    - ctx: CanvasRenderingContext2D for rendering overlay vector graphics.
 *    - symbol: Currently active instrument symbol.
 *    - series: Attached Lightweight Charts series primitive reference.
 *
 * 3. Technologies used and why:
 *    HTML5 Canvas 2D API for high-performance 60-120 FPS drawing rendering,
 *    Lightweight Charts v5 series primitive API for seamless canvas synchronization,
 *    and typed async REST API methods for lossless backend persistence.
 *
 * 4. Key design and overall design of the class:
 *    Provides dual-mode rendering (dedicated overlay canvas + series primitive fallback),
 *    exact Euclidean and point-in-polygon hit-testing with the M6-13 Long/Short bug fix,
 *    and reactive event delegation for mouse, pointer, and keyboard operations.
 */
export class DrawingLayer {
  /**
   * 1. The use of function:
   *    Initializes the DrawingLayer state and registers internal Lightweight Charts view definition.
   *
   * 2. How does the specific function work:
   *    Binds chart reference, initializes internal collections (items, temp, selected),
   *    and creates the _view primitive descriptor configured with zOrder "top".
   *
   * 3. Concepts used in the function:
   *    Object initialization, series primitive contract.
   *
   * 4. Places where this function is imported and used:
   *    Instantiated inside QuantChart constructor in apps/web/js/chart.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Fully initialized DrawingLayer ready for canvas attachment.
   */
  constructor(chart) {
    this.chart = chart;
    this.items = [];
    this.temp = null;
    this.selected = null;
    this.tool = "cursor";
    this.canvas = null;
    this.ctx = null;
    this.symbol = chart?.symbol || "NSE:NIFTY50";
    this.series = null;
    this.requestUpdate = null;

    this._view = {
      zOrder: () => "top",
      renderer: () => ({
        draw: (target) =>
          target.useMediaCoordinateSpace(({ context, mediaSize }) =>
            this.draw(context, mediaSize),
          ),
      }),
    };
  }

  /**
   * 1. The use of function:
   *    Mounts the transparent overlay canvas inside the chart DOM container.
   *
   * 2. How does the specific function work:
   *    Ensures container has relative positioning, creates transparent <canvas> element,
   *    binds pointer, mouse, and resize listeners, and attaches it as a child of container.
   *
   * 3. Concepts used in the function:
   *    DOM manipulation, canvas layering, event listener binding.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by QuantChart.initChart() during workstation mounting.
   *
   * 5. Final output of the function, before and after:
   *    Before: Container without overlay canvas. After: Overlay canvas mounted and listening to events.
   */
  mount(container) {
    if (!container) return;
    this.container = container;
    this.container.style.position = "relative";

    this.canvas = document.createElement("canvas");
    this.canvas.className = "quantview-drawing-overlay";
    this.canvas.style.position = "absolute";
    this.canvas.style.top = "0";
    this.canvas.style.left = "0";
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    this.canvas.style.zIndex = "4";
    this.canvas.style.pointerEvents = "none";

    this.ctx = this.canvas.getContext("2d");
    this.container.appendChild(this.canvas);

    this.bindOverlayEvents();
    this.syncResize();
  }

  /**
   * 1. The use of function:
   *    Binds interactive pointer and mouse events to the overlay canvas and chart container.
   *
   * 2. How does the specific function work:
   *    Attaches pointerdown, pointermove, pointerup, click, and contextmenu listeners
   *    to handle interactive point placement, selection, and hit-testing.
   *
   * 3. Concepts used in the function:
   *    Pointer events, mouse tracking, canvas event delegation.
   *
   * 4. Places where this function is imported and used:
   *    Called internally by mount().
   *
   * 5. Final output of the function, before and after:
   *    Before: Detached events. After: Overlay canvas bound to user input gestures.
   */
  bindOverlayEvents() {
    if (!this.canvas) return;

    this.canvas.addEventListener("pointerdown", (e) => this.onPointerDown(e));
    this.canvas.addEventListener("pointermove", (e) => this.onPointerMove(e));
    this.canvas.addEventListener("pointerup", (e) => this.onPointerUp(e));
    this.canvas.addEventListener("click", (e) => this.onCanvasClick(e));

    // Also observe container mousemove for cursor hit-testing when in cursor mode
    this.container.addEventListener("mousemove", (e) => {
      if (this.tool === "cursor" && !this.temp) {
        const rect = this.container.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const hit = this.hitTest(x, y);
        if (hit) {
          this.canvas.style.pointerEvents = "auto";
          this.canvas.style.cursor = "pointer";
        } else {
          this.canvas.style.pointerEvents = "none";
          this.canvas.style.cursor = "";
        }
      }
    });
  }

  /**
   * 1. The use of function:
   *    Lifecycle hook called when DrawingLayer is attached to a Lightweight Charts series.
   *
   * 2. How does the specific function work:
   *    Stores the series instance and the requestUpdate callback provided by the chart.
   *
   * 3. Concepts used in the function:
   *    Lightweight Charts ISeriesPrimitive lifecycle contract.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Lightweight Charts when series.attachPrimitive(this) is called.
   *
   * 5. Final output of the function, before and after:
   *    Before: this.series is null. After: Series reference and update callback registered.
   */
  attached({ series, requestUpdate }) {
    this.series = series;
    this.requestUpdate = requestUpdate;
  }

  /**
   * 1. The use of function:
   *    Lifecycle hook called when DrawingLayer is detached from a Lightweight Charts series.
   *
   * 2. How does the specific function work:
   *    Clears the internal series reference.
   *
   * 3. Concepts used in the function:
   *    Lightweight Charts ISeriesPrimitive teardown.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Lightweight Charts when series.detachPrimitive(this) is called.
   *
   * 5. Final output of the function, before and after:
   *    Before: Series attached. After: Series detached and pointer nullified.
   */
  detached() {
    this.series = null;
    this.requestUpdate = null;
  }

  /**
   * 1. The use of function:
   *    Lightweight Charts primitive method required by ISeriesPrimitive contract.
   *
   * 2. How does the specific function work:
   *    No-op implementation satisfied for primitive interface compliance.
   *
   * 3. Concepts used in the function:
   *    Interface protocol conformance.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Lightweight Charts render pipeline.
   *
   * 5. Final output of the function, before and after:
   *    Before: N/A. After: Interface protocol satisfied.
   */
  updateAllViews() {}

  /**
   * 1. The use of function:
   *    Returns the pane views for Lightweight Charts primitive rendering.
   *
   * 2. How does the specific function work:
   *    Returns single-element array containing the internal _view renderer.
   *
   * 3. Concepts used in the function:
   *    Lightweight Charts pane view provider.
   *
   * 4. Places where this function is imported and used:
   *    Queried by Lightweight Charts primitive rendering loop.
   *
   * 5. Final output of the function, before and after:
   *    Before: Query initiated. After: Returns [this._view].
   */
  paneViews() {
    return [this._view];
  }

  /**
   * 1. The use of function:
   *    Triggers an immediate repaint of both the overlay canvas and the series primitive.
   *
   * 2. How does the specific function work:
   *    Invokes drawOverlay() to repaint the 2D canvas and calls this.requestUpdate?.().
   *
   * 3. Concepts used in the function:
   *    Repaint notification, render loop synchronization.
   *
   * 4. Places where this function is imported and used:
   *    Invoked after adding, modifying, selecting, or deleting any drawing.
   *
   * 5. Final output of the function, before and after:
   *    Before: Stale canvas pixels. After: Repainted canvas with updated vector annotations.
   */
  update() {
    this.drawOverlay();
    this.requestUpdate?.();
  }

  /**
   * 1. The use of function:
   *    Converts a UTC epoch second timestamp into a horizontal canvas X pixel coordinate.
   *
   * 2. How does the specific function work:
   *    Delegates to this.chart.timeToX(t).
   *
   * 3. Concepts used in the function:
   *    Time scale projection, coordinate mapping.
   *
   * 4. Places where this function is imported and used:
   *    Invoked throughout drawOne() and hitTest() during geometric calculations.
   *
   * 5. Final output of the function, before and after:
   *    Before: UTC timestamp. After: Canvas X pixel coordinate (number or null).
   */
  x(t) {
    if (this.chart && typeof this.chart.timeToX === "function") {
      return this.chart.timeToX(t);
    }
    return null;
  }

  /**
   * 1. The use of function:
   *    Converts a price float into a vertical canvas Y pixel coordinate.
   *
   * 2. How does the specific function work:
   *    Delegates to this.chart.priceToY(p) or this.series.priceToCoordinate(p).
   *
   * 3. Concepts used in the function:
   *    Price scale projection, coordinate mapping.
   *
   * 4. Places where this function is imported and used:
   *    Invoked throughout drawOne() and hitTest() during geometric calculations.
   *
   * 5. Final output of the function, before and after:
   *    Before: Price level. After: Canvas Y pixel coordinate (number or null).
   */
  y(p) {
    if (this.chart && typeof this.chart.priceToY === "function") {
      return this.chart.priceToY(p);
    }
    return this.series?.priceToCoordinate(p) ?? null;
  }

  /**
   * 1. The use of function:
   *    Formats a numerical price using the application's Indian Rupee monetary formatter.
   *
   * 2. How does the specific function work:
   *    Delegates to fmtPrice(v).
   *
   * 3. Concepts used in the function:
   *    Monetary formatting, locale presentation.
   *
   * 4. Places where this function is imported and used:
   *    Used when rendering price labels on horizontal lines, Fibonacci levels, and Long/Short boxes.
   *
   * 5. Final output of the function, before and after:
   *    Before: Float price. After: Formatted price string (e.g. "24,850.50").
   */
  formatPrice(v) {
    return fmtPrice(v);
  }

  /**
   * 1. The use of function:
   *    Updates the active drawing items array in memory and resets selection.
   *
   * 2. How does the specific function work:
   *    Assigns this.items, clears this.selected, and triggers an update repaint.
   *
   * 3. Concepts used in the function:
   *    State replacement, canvas repaint.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by loadDrawingsFromBackend() and chart initialization routines.
   *
   * 5. Final output of the function, before and after:
   *    Before: Previous drawing items. After: Updated drawing items rendered on canvas.
   */
  setItems(items) {
    this.items = items || [];
    this.selected = null;
    this.update();
  }

  /**
   * 1. The use of function:
   *    Sets the active drawing tool mode (e.g. "cursor", "trend", "long", "short").
   *
   * 2. How does the specific function work:
   *    Updates this.tool property, cancels any incomplete in-flight drawing (this.temp),
   *    updates canvas pointer-events and cursor styling, and repaints.
   *
   * 3. Concepts used in the function:
   *    Tool state management, mode switching, pointer-events configuration.
   *
   * 4. Places where this function is imported and used:
   *    Invoked when user clicks toolbar buttons in #drawbar.
   *
   * 5. Final output of the function, before and after:
   *    Before: Previous tool mode. After: Updated tool mode with appropriate cursor styling.
   */
  setTool(tool) {
    this.tool = tool || "cursor";
    if (this.temp) {
      this.temp = null;
    }
    if (this.canvas) {
      if (this.tool === "cursor") {
        this.canvas.style.pointerEvents = "none";
        this.canvas.style.cursor = "";
      } else {
        this.canvas.style.pointerEvents = "auto";
        this.canvas.style.cursor = "crosshair";
      }
    }
    this.update();
  }

  /**
   * 1. The use of function:
   *    Repaints the transparent overlay canvas using the Canvas 2D context.
   *
   * 2. How does the specific function work:
   *    Clears the rectangular canvas area and executes this.draw(ctx, { width, height }).
   *
   * 3. Concepts used in the function:
   *    Canvas 2D clearRect, vector rendering pass.
   *
   * 4. Places where this function is imported and used:
   *    Called on every state change, scroll, zoom, and mouse movement.
   *
   * 5. Final output of the function, before and after:
   *    Before: Previous canvas pixels. After: Repainted overlay canvas.
   */
  drawOverlay() {
    if (!this.ctx || !this.canvas) return;
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (w <= 0 || h <= 0) return;

    this.ctx.clearRect(0, 0, w, h);
    this.draw(this.ctx, { width: w, height: h });
  }

  /**
   * 1. The use of function:
   *    Primary vector rendering loop drawing all completed items and temporary in-progress drawings.
   *
   * 2. How does the specific function work:
   *    Saves context state, sets typography font, iterates over items and temp drawing,
   *    and delegates each item to drawOne(). Restores context state on completion.
   *
   * 3. Concepts used in the function:
   *    Canvas state preservation, font styling, iterative drawing execution.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by drawOverlay() and Lightweight Charts primitive renderer.
   *
   * 5. Final output of the function, before and after:
   *    Before: Canvas context ready. After: All drawing annotations rendered.
   */
  draw(ctx, size) {
    ctx.save();
    ctx.font = "11px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    const allDrawings = [...this.items, ...(this.temp ? [this.temp] : [])];
    for (const d of allDrawings) {
      try {
        this.drawOne(ctx, size, d, d === this.selected || d === this.temp);
      } catch {
        /* drawing off-screen or coordinates not yet projected */
      }
    }
    ctx.restore();
  }

  /**
   * 1. The use of function:
   *    Renders an individual drawing item onto the target Canvas 2D context.
   *
   * 2. How does the specific function work:
   *    Projects all anchor points to (x, y) coordinates. Dispatches switch based on d.type
   *    (trend, ray, extended, hline, hray, vline, channel, rect, fib, measure, long, short, text)
   *    rendering stroke lines, polygon fills, price tags, and selection anchor handles.
   *
   * 3. Concepts used in the function:
   *    Vector path construction, geometric projection, typography metrics, selection handles.
   *
   * 4. Places where this function is imported and used:
   *    Called internally by draw() for each active drawing item.
   *
   * 5. Final output of the function, before and after:
   *    Before: Unrendered drawing object. After: Vector primitives rendered on canvas.
   */
  drawOne(ctx, size, d, active) {
    const pts = d.points.map((p) => ({
      x: this.x(p.time),
      y: this.y(p.price),
      ...p,
    }));
    if (pts.some((p) => p.x == null || p.y == null)) return;

    const color = d.color || COLORS.line;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = active ? 2 : 1.5;
    ctx.setLineDash([]);
    const [a, b, c] = pts;

    const line = (x1, y1, x2, y2) => {
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    };

    const label = (txt, x, y, align = "left", bg = null) => {
      ctx.textAlign = align;
      ctx.textBaseline = "middle";
      if (bg) {
        const w = ctx.measureText(txt).width + 10;
        ctx.fillStyle = bg;
        ctx.fillRect(
          align === "center" ? x - w / 2 : align === "right" ? x - w : x,
          y - 9,
          w,
          18,
        );
        ctx.fillStyle = "#ffffff";
        ctx.fillText(
          txt,
          align === "center" ? x : align === "right" ? x - 5 : x + 5,
          y,
        );
        ctx.fillStyle = color;
      } else {
        ctx.fillText(txt, x, y);
      }
    };

    const extend = (p, q, both) => {
      const dx = q.x - p.x;
      const dy = q.y - p.y;
      if (dx === 0 && dy === 0) return [p, q];
      const far = 1e5;
      const len = Math.hypot(dx, dy) || 1;
      const e2 = { x: p.x + (dx / len) * far, y: p.y + (dy / len) * far };
      const e1 = both
        ? { x: p.x - (dx / len) * far, y: p.y - (dy / len) * far }
        : p;
      return [e1, e2];
    };

    const price = (v) => this.formatPrice(v);

    switch (d.type) {
      case "trend":
        if (b) line(a.x, a.y, b.x, b.y);
        break;

      case "ray": {
        if (b) {
          const [p, q] = extend(a, b, false);
          line(p.x, p.y, q.x, q.y);
        }
        break;
      }

      case "extended": {
        if (b) {
          const [p, q] = extend(a, b, true);
          line(p.x, p.y, q.x, q.y);
        }
        break;
      }

      case "hline":
        line(0, a.y, size.width, a.y);
        label(price(a.price), size.width - 4, a.y - 10, "right");
        break;

      case "hray":
        line(a.x, a.y, size.width, a.y);
        label(price(a.price), size.width - 4, a.y - 10, "right");
        break;

      case "vline":
        line(a.x, 0, a.x, size.height);
        break;

      case "channel": {
        if (b) {
          line(a.x, a.y, b.x, b.y);
          if (c) {
            const off =
              c.y - (a.y + ((b.y - a.y) * (c.x - a.x)) / (b.x - a.x || 1));
            line(a.x, a.y + off, b.x, b.y + off);
            ctx.globalAlpha = 0.08;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.lineTo(b.x, b.y + off);
            ctx.lineTo(a.x, a.y + off);
            ctx.closePath();
            ctx.fill();
            ctx.globalAlpha = 1;
          }
        }
        break;
      }

      case "rect": {
        if (b) {
          ctx.globalAlpha = 0.12;
          ctx.fillRect(a.x, a.y, b.x - a.x, b.y - a.y);
          ctx.globalAlpha = 1;
          ctx.strokeRect(a.x, a.y, b.x - a.x, b.y - a.y);
        }
        break;
      }

      case "fib": {
        if (b) {
          const x1 = Math.min(a.x, b.x);
          const x2 = Math.max(a.x, b.x);
          ctx.strokeStyle = d.color || COLORS.fib;
          for (const lv of FIB_LEVELS) {
            const p = b.price + (a.price - b.price) * lv;
            const y = this.y(p);
            if (y == null) continue;
            ctx.globalAlpha = lv === 0.5 || lv === 0.618 ? 1 : 0.7;
            line(x1, y, x2, y);
            ctx.globalAlpha = 1;
            ctx.fillStyle = d.color || COLORS.fib;
            label(`${lv} (${price(p)})`, x1 + 2, y - 8);
          }
          ctx.setLineDash([3, 3]);
          line(a.x, a.y, b.x, b.y);
          ctx.setLineDash([]);
        }
        break;
      }

      case "measure": {
        if (b) {
          const up = b.price >= a.price;
          ctx.fillStyle = (up ? COLORS.up : COLORS.down) + "0.15)";
          ctx.fillRect(a.x, a.y, b.x - a.x, b.y - a.y);
          ctx.strokeStyle = (up ? COLORS.up : COLORS.down) + "1)";
          line((a.x + b.x) / 2, a.y, (a.x + b.x) / 2, b.y);
          const logicalA = this.chart?.logicalOf?.(a.time) ?? 0;
          const logicalB = this.chart?.logicalOf?.(b.time) ?? 0;
          const bars = Math.round(logicalB - logicalA);
          const diff = b.price - a.price;
          const pct = (diff / a.price) * 100;
          ctx.fillStyle = (up ? COLORS.up : COLORS.down) + "1)";
          label(
            `${diff >= 0 ? "+" : ""}${price(diff)} (${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%)  ${bars} bars`,
            (a.x + b.x) / 2,
            b.y + (up ? -14 : 14),
            "center",
            (up ? COLORS.up : COLORS.down) + "0.9)",
          );
        }
        break;
      }

      case "long":
      case "short": {
        if (b) {
          const dir = d.type === "long" ? 1 : -1;
          const risk = Math.abs(a.price - b.price) || a.price * 0.01;
          const stop = a.price - dir * risk;
          const target = a.price + dir * risk * (d.rr || 2);
          const ys = this.y(stop);
          const yt = this.y(target);
          const x1 = Math.min(a.x, b.x);
          const w = Math.max(Math.abs(b.x - a.x), 40);

          if (ys != null && yt != null) {
            ctx.fillStyle = COLORS.up + "0.18)";
            ctx.fillRect(x1, a.y, w, yt - a.y);
            ctx.fillStyle = COLORS.down + "0.18)";
            ctx.fillRect(x1, a.y, w, ys - a.y);
            ctx.strokeStyle = "#787b86";
            line(x1, a.y, x1 + w, a.y);

            ctx.fillStyle = COLORS.up + "1)";
            label(
              `Target ${price(target)} (${(((target - a.price) / a.price) * 100 * dir).toFixed(2)}%)`,
              x1 + w / 2,
              yt + (dir > 0 ? 10 : -10),
              "center",
              COLORS.up + "0.9)",
            );

            label(
              `Stop ${price(stop)} (${(((a.price - stop) / a.price) * 100 * dir).toFixed(2)}%)`,
              x1 + w / 2,
              ys + (dir > 0 ? -10 : 10),
              "center",
              COLORS.down + "0.9)",
            );

            ctx.fillStyle = "#787b86";
            label(
              `Entry ${price(a.price)}  R:R ${(d.rr || 2).toFixed(1)}`,
              x1 + 4,
              a.y - 9,
            );
          }
        }
        break;
      }

      case "text": {
        ctx.font = "13px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
        label(d.text || "Note", a.x, a.y, "left", d.color || COLORS.line);
        break;
      }

      default:
        break;
    }

    // Render anchor handle points if active/selected
    if (active) {
      ctx.fillStyle = "#ffffff";
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      for (const p of pts) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
    }
  }

  /**
   * 1. The use of function:
   *    Performs precise geometric hit-testing to identify the nearest drawing within interaction range.
   *
   * 2. How does the specific function work:
   *    Iterates through all items, projects points to canvas space, and calculates distance
   *    to geometries. Applies the verified M6-13 bounding box calculation for Long and Short
   *    positions ensuring clicking anywhere in target, entry, or stop zones selects the box.
   *
   * 3. Concepts used in the function:
   *    Point-to-segment Euclidean distance, axis-aligned bounding box containment, M6-13 hit-test fix.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by pointer event handlers when user clicks in cursor mode to select drawings.
   *
   * 5. Final output of the function, before and after:
   *    Before: Click coordinates (x, y). After: Nearest hit drawing object or null.
   */
  hitTest(x, y) {
    let best = null;
    let bestD = 7;

    const segDist = (p, q) => {
      const dx = q.x - p.x;
      const dy = q.y - p.y;
      const l2 = dx * dx + dy * dy;
      const t = l2
        ? Math.max(0, Math.min(1, ((x - p.x) * dx + (y - p.y) * dy) / l2))
        : 0;
      return Math.hypot(x - (p.x + t * dx), y - (p.y + t * dy));
    };

    for (const d of this.items) {
      const pts = d.points.map((p) => ({
        x: this.x(p.time),
        y: this.y(p.price),
        ...p,
      }));
      if (pts.some((p) => p.x == null || p.y == null)) continue;
      const [a, b, c] = pts;
      let dist = Infinity;

      if (d.type === "hline") {
        dist = Math.abs(y - a.y);
      } else if (d.type === "hray") {
        dist = x >= a.x - 4 ? Math.abs(y - a.y) : Infinity;
      } else if (d.type === "vline") {
        dist = Math.abs(x - a.x);
      } else if (d.type === "text") {
        dist =
          x >= a.x - 4 && x <= a.x + 120 && Math.abs(y - a.y) < 14
            ? 0
            : Infinity;
      } else if (["rect", "fib", "measure"].includes(d.type) && b) {
        const inside =
          x >= Math.min(a.x, b.x) - 4 &&
          x <= Math.max(a.x, b.x, a.x + 40) + 4 &&
          y >= Math.min(a.y, b.y) - 40 &&
          y <= Math.max(a.y, b.y) + 40;
        dist = inside ? 3 : Infinity;
      } else if (["long", "short"].includes(d.type) && b) {
        // --- Verified M6-13 Hit-Test Bug Fix for Long/Short Positions ---
        const dir = d.type === "long" ? 1 : -1;
        const risk = Math.abs(a.price - b.price) || a.price * 0.01;
        const stop = a.price - dir * risk;
        const target = a.price + dir * risk * (d.rr || 2);
        const ys = this.y(stop);
        const yt = this.y(target);
        if (ys != null && yt != null) {
          const minY = Math.min(a.y, ys, yt) - 6;
          const maxY = Math.max(a.y, ys, yt) + 6;
          const minX = Math.min(a.x, b.x) - 4;
          const maxX = Math.max(a.x, b.x, a.x + 40) + 4;
          const inside = x >= minX && x <= maxX && y >= minY && y <= maxY;
          dist = inside ? 3 : Infinity;
        }
      } else if (d.type === "channel" && a && b && c) {
        const d1 = segDist(a, b);
        const off =
          c.y - (a.y + ((b.y - a.y) * (c.x - a.x)) / (b.x - a.x || 1));
        const c2 = { x: b.x, y: b.y + off };
        const c1 = { x: a.x, y: a.y + off };
        const d2 = segDist(c1, c2);
        dist = Math.min(d1, d2);
      } else if (b) {
        const far = (p, q, both) => {
          const dx = q.x - p.x;
          const dy = q.y - p.y;
          const len = Math.hypot(dx, dy) || 1;
          return [
            both ? { x: p.x - (dx / len) * 1e5, y: p.y - (dy / len) * 1e5 } : p,
            { x: p.x + (dx / len) * 1e5, y: p.y + (dy / len) * 1e5 },
          ];
        };
        const [p, q] =
          d.type === "ray"
            ? far(a, b, false)
            : d.type === "extended"
              ? far(a, b, true)
              : [a, b];
        dist = segDist(p, q);
      }

      if (dist < bestD) {
        bestD = dist;
        best = d;
      }
    }
    return best;
  }

  /**
   * 1. The use of function:
   *    Resolves canvas coordinate (x, y) into a chart coordinate { time, price }.
   *
   * 2. How does the specific function work:
   *    Invokes parent chart methods coordinateToPrice and timeOfLogical to convert pixel space.
   *
   * 3. Concepts used in the function:
   *    Inverse coordinate projection, time/price scale conversion.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by pointer down/move handlers when creating or updating anchor points.
   *
   * 5. Final output of the function, before and after:
   *    Before: Canvas (x, y). After: Point object { time: UtcEpochSec, price: number } or null.
   */
  pointAt(x, y) {
    if (!this.chart) return null;
    return this.chart.pointAtXY?.(x, y) ?? null;
  }

  /**
   * 1. The use of function:
   *    Handles pointerdown events for drawing tool point anchoring and selection.
   *
   * 2. How does the specific function work:
   *    Calculates relative coordinates, checks if in cursor mode (hit-testing) or drawing mode
   *    (point creation). If drawing, initializes or extends this.temp anchor points.
   *
   * 3. Concepts used in the function:
   *    Pointer interaction, anchor point accumulation, mode branching.
   *
   * 4. Places where this function is imported and used:
   *    Registered on overlay canvas in bindOverlayEvents().
   *
   * 5. Final output of the function, before and after:
   *    Before: Pointer event received. After: State updated, drawing initialized or selected.
   */
  onPointerDown(e) {
    if (!this.canvas) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (this.tool === "cursor") {
      this.selected = this.hitTest(x, y);
      this.update();
      return;
    }

    const def = TOOL_BY_ID[this.tool];
    const pt = this.pointAt(x, y);
    if (!def || !pt) return;

    if (!this.temp) {
      this.temp = {
        id: "draw-" + Math.random().toString(36).substring(2, 10),
        type: this.tool,
        points: [pt],
      };
      if (def.points > 1) {
        this.temp.points.push({ ...pt });
      }
    } else {
      this.temp.points[this.temp.points.length - 1] = pt;
      if (this.temp.points.length < def.points) {
        this.temp.points.push({ ...pt });
      } else {
        this.temp.done = true;
      }
    }

    if (def.points <= 1) {
      this.temp.done = true;
    }

    if (this.temp.done) {
      this.finalizeCurrentDrawing();
    }
    this.update();
  }

  /**
   * 1. The use of function:
   *    Handles pointermove events to provide real-time preview of drawings in progress.
   *
   * 2. How does the specific function work:
   *    If this.temp is active, updates the last anchor point to match current cursor position
   *    and triggers update() to repaint the preview at 60 FPS.
   *
   * 3. Concepts used in the function:
   *    Live preview rendering, temporal point tracking.
   *
   * 4. Places where this function is imported and used:
   *    Registered on overlay canvas in bindOverlayEvents().
   *
   * 5. Final output of the function, before and after:
   *    Before: Stale preview line. After: Real-time updated vector preview under cursor.
   */
  onPointerMove(e) {
    if (!this.canvas || !this.temp) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const pt = this.pointAt(x, y);
    if (!pt) return;

    this.temp.points[this.temp.points.length - 1] = pt;
    this.update();
  }

  /**
   * 1. The use of function:
   *    Handles pointerup events concluding a drag or click gesture.
   *
   * 2. How does the specific function work:
   *    Placeholder for future drag-to-resize gesture release; maintains current drawing state.
   *
   * 3. Concepts used in the function:
   *    Gesture lifecycle completion.
   *
   * 4. Places where this function is imported and used:
   *    Registered on overlay canvas in bindOverlayEvents().
   *
   * 5. Final output of the function, before and after:
   *    Before: Active gesture. After: Completed pointer gesture.
   */
  onPointerUp(_e) {}

  /**
   * 1. The use of function:
   *    Handles direct click events on the overlay canvas.
   *
   * 2. How does the specific function work:
   *    Evaluates click coordinates and satisfies hit-test selection if in cursor mode.
   *
   * 3. Concepts used in the function:
   *    Click delegation, selection dispatch.
   *
   * 4. Places where this function is imported and used:
   *    Registered on overlay canvas in bindOverlayEvents().
   *
   * 5. Final output of the function, before and after:
   *    Before: Click received. After: Selected item updated.
   */
  onCanvasClick(e) {
    if (this.tool === "cursor") {
      const rect = this.canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      this.selected = this.hitTest(x, y);
      this.update();
    }
  }

  /**
   * 1. The use of function:
   *    Lightweight Charts subscribeClick adapter forwarding chart clicks to drawing layer.
   *
   * 2. How does the specific function work:
   *    Extracts point from Lightweight Charts event payload and executes onPointerDown logic.
   *
   * 3. Concepts used in the function:
   *    Chart event adaptation.
   *
   * 4. Places where this function is imported and used:
   *    Registered via chart.subscribeClick in QuantChart.
   *
   * 5. Final output of the function, before and after:
   *    Before: Chart click. After: Drawing selection or point creation dispatched.
   */
  onClick(p) {
    if (this.tool === "cursor" && p?.point) {
      this.selected = this.hitTest(p.point.x, p.point.y);
      this.update();
    }
  }

  /**
   * 1. The use of function:
   *    Lightweight Charts subscribeCrosshairMove adapter updating temp drawing previews.
   *
   * 2. How does the specific function work:
   *    If temp drawing is active and crosshair coordinate is available, updates last point.
   *
   * 3. Concepts used in the function:
   *    Crosshair synchronization, live preview.
   *
   * 4. Places where this function is imported and used:
   *    Registered via chart.subscribeCrosshairMove in QuantChart.
   *
   * 5. Final output of the function, before and after:
   *    Before: Stale preview. After: Live preview updated to crosshair position.
   */
  onCrosshair(p) {
    if (this.tool !== "cursor" && this.temp && p?.point) {
      const pt = this.pointAt(p.point.x, p.point.y);
      if (pt) {
        this.temp.points[this.temp.points.length - 1] = pt;
        this.update();
      }
    }
  }

  /**
   * 1. The use of function:
   *    Finalizes the currently constructed temporary drawing and persists it to backend.
   *
   * 2. How does the specific function work:
   *    Extracts this.temp, prompts for text note content if type === "text", pushes item
   *    to this.items, sets this.selected, dispatches saveDrawingToBackend(), and resets tool to cursor.
   *
   * 3. Concepts used in the function:
   *    Drawing finalization, prompt dialogue, backend persistence dispatch.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by onPointerDown when required number of anchor points is satisfied.
   *
   * 5. Final output of the function, before and after:
   *    Before: In-progress temp drawing. After: Persisted drawing item added to active items.
   */
  finalizeCurrentDrawing() {
    if (!this.temp) return;
    const item = this.temp;
    delete item.done;
    this.temp = null;

    if (item.type === "text") {
      const note = window.prompt("Enter text note:", "");
      if (!note) {
        this.setTool("cursor");
        this.update();
        return;
      }
      item.text = note;
    }

    this.items.push(item);
    this.selected = item;
    this.saveDrawingToBackend(item);
    this.setTool("cursor");
  }

  /**
   * 1. The use of function:
   *    Cancels in-progress drawing construction or clears current selection.
   *
   * 2. How does the specific function work:
   *    Clears this.temp, resets this.tool to "cursor", deselects active item, and updates canvas.
   *
   * 3. Concepts used in the function:
   *    Cancellation semantics, escape key recovery.
   *
   * 4. Places where this function is imported and used:
   *    Invoked when Escape key is pressed or when switching away from drawing mode.
   *
   * 5. Final output of the function, before and after:
   *    Before: In-progress or selected drawing. After: Clean idle cursor state.
   */
  cancel() {
    this.temp = null;
    this.selected = null;
    this.setTool("cursor");
    this.update();
  }

  /**
   * 1. The use of function:
   *    Persists a drawing record to the FastAPI backend storage via POST /api/v1/charts/drawings.
   *
   * 2. How does the specific function work:
   *    Formats drawing entity into DrawingRecord schema and calls api.saveDrawing().
   *
   * 3. Concepts used in the function:
   *    REST persistence, schema serialization, error suppression.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by finalizeCurrentDrawing() upon completing a new drawing.
   *
   * 5. Final output of the function, before and after:
   *    Before: Memory-only drawing. After: Drawing persisted to backend JSON/DuckDB lake storage.
   */
  async saveDrawingToBackend(drawing) {
    try {
      const record = {
        id: drawing.id,
        symbol: this.symbol,
        type: drawing.type,
        points: drawing.points.map((p) => ({
          time: Math.round(p.time),
          price: Number(p.price),
        })),
        properties: {
          color: drawing.color || null,
          rr: drawing.rr || 2,
          text: drawing.text || "",
        },
      };
      await api.saveDrawing(record);
    } catch (err) {
      console.error("[DrawingLayer] Failed to save drawing to backend:", err);
    }
  }

  /**
   * 1. The use of function:
   *    Loads saved chart drawing annotations from the backend via GET /api/v1/charts/drawings.
   *
   * 2. How does the specific function work:
   *    Queries api.getDrawings(symbol), converts DrawingRecord payloads into local drawing items,
   *    updates this.items, and repaints the canvas.
   *
   * 3. Concepts used in the function:
   *    State hydration, backend query, chart annotation restoration.
   *
   * 4. Places where this function is imported and used:
   *    Invoked upon initial chart load and whenever the symbol changes.
   *
   * 5. Final output of the function, before and after:
   *    Before: Empty or stale drawings. After: Restored drawings for the current instrument symbol.
   */
  async loadDrawingsFromBackend(symbol) {
    try {
      this.symbol = symbol || this.symbol;
      const records = await api.getDrawings(this.symbol);
      if (Array.isArray(records)) {
        this.items = records.map((r) => ({
          id: r.id,
          type: r.type,
          points: (r.points || []).map((p) => ({
            time: p.time,
            price: p.price,
          })),
          color: r.properties?.color || null,
          rr: r.properties?.rr || 2,
          text: r.properties?.text || "",
        }));
        this.selected = null;
        this.update();
      }
    } catch (err) {
      console.error("[DrawingLayer] Failed to load drawings from backend:", err);
    }
  }

  /**
   * 1. The use of function:
   *    Deletes the currently selected drawing annotation from memory and backend storage.
   *
   * 2. How does the specific function work:
   *    If this.selected exists, removes it from this.items, clears selection, updates canvas,
   *    and dispatches DELETE /api/v1/charts/drawings/{id} via api.deleteDrawing().
   *
   * 3. Concepts used in the function:
   *    Resource deletion, REST DELETE, instant UI reactivity.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Delete/Backspace keyboard shortcuts and trash button in #drawbar.
   *
   * 5. Final output of the function, before and after:
   *    Before: Selected drawing present. After: Drawing purged from canvas and backend disk storage.
   */
  async deleteSelectedDrawing() {
    if (!this.selected) return false;
    const drawingId = this.selected.id;
    this.items = this.items.filter((x) => x !== this.selected);
    this.selected = null;
    this.update();

    if (drawingId) {
      try {
        await api.deleteDrawing(drawingId);
      } catch (err) {
        console.error("[DrawingLayer] Failed to delete drawing from backend:", err);
      }
    }
    return true;
  }

  /**
   * 1. The use of function:
   *    Purges all drawings for the active symbol from memory and backend storage.
   *
   * 2. How does the specific function work:
   *    Clears this.items, this.selected, and this.temp, updates canvas, and dispatches
   *    DELETE /api/v1/charts/drawings?symbol=... via api.clearDrawings().
   *
   * 3. Concepts used in the function:
   *    Bulk deletion, symbol purge, canvas reset.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by clear button in #drawbar.
   *
   * 5. Final output of the function, before and after:
   *    Before: Drawings on canvas. After: Canvas completely cleared and backend purged.
   */
  async clearDrawings() {
    this.items = [];
    this.selected = null;
    this.temp = null;
    this.update();

    try {
      await api.clearDrawings(this.symbol);
    } catch (err) {
      console.error("[DrawingLayer] Failed to clear drawings from backend:", err);
    }
  }

  /**
   * 1. The use of function:
   *    Synchronizes overlay canvas pixel dimensions and device pixel ratio with the chart container.
   *
   * 2. How does the specific function work:
   *    Measures container clientWidth and clientHeight, applies devicePixelRatio scaling,
   *    and triggers update() to repaint vector graphics cleanly without blurring.
   *
   * 3. Concepts used in the function:
   *    High-DPI canvas scaling, resize synchronization.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by QuantChart.syncResize() when workstation layout changes.
   *
   * 5. Final output of the function, before and after:
   *    Before: Possible canvas resolution mismatch. After: Pixel-perfect crisp vector canvas.
   */
  syncResize() {
    if (!this.canvas || !this.container) return;
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    if (w <= 0 || h <= 0) return;

    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.floor(w * dpr);
    this.canvas.height = Math.floor(h * dpr);
    this.canvas.style.width = w + "px";
    this.canvas.style.height = h + "px";

    if (this.ctx) {
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    this.drawOverlay();
  }

  /**
   * 1. The use of function:
   *    Tears down the overlay canvas and cleans up event listeners.
   *
   * 2. How does the specific function work:
   *    Removes canvas element from DOM, cleans up references, and sets pointers to null.
   *
   * 3. Concepts used in the function:
   *    Resource disposal, DOM cleanup.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by QuantChart.destroy() during unmounting.
   *
   * 5. Final output of the function, before and after:
   *    Before: Active overlay canvas. After: Overlay canvas removed and resources freed.
   */
  destroy() {
    if (this.canvas && this.canvas.parentNode) {
      this.canvas.parentNode.removeChild(this.canvas);
    }
    this.canvas = null;
    this.ctx = null;
    this.items = [];
    this.temp = null;
    this.selected = null;
  }
}
