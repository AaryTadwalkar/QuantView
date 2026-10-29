/**
 * 1. What this file does:
 *    TradingView Lightweight Charts v5 integration wrapper for QuantView (apps/web/js/chart.js).
 *    Manages the primary chart canvas, candlestick and volume series, chart type transforms (Candles,
 *    Heikin Ashi, Line, Area), time scale projection in Indian Standard Time (IST, UTC+05:30),
 *    backtest entry/exit trade markers, on-chart SL/TP price lines, and viewport resizing
 *    (Milestones M6-01, M6-03, M6-03b, M6-07, M6-09, M6-12, M6-18, and Gate G4).
 *
 * 2. Overall design:
 *    - Encapsulates TradingView Lightweight Charts v5 in a clean QuantChart class.
 *    - Adheres to the TradingView dark theme palette (--bg: #131722, --panel: #1e222d, --up: #089981, --down: #f23645).
 *    - Implements deterministic UtcEpochSec time formatting to IST (Asia/Kolkata, UTC+05:30).
 *    - Manages main price series and sub-scale volume histogram overlay.
 *    - Supports instant switching between Candlestick, Heikin Ashi, Line, and Area series.
 *    - Displays an amber advisory banner when synthetic Heikin Ashi transforms are active.
 *    - Provides high-level methods for marker overlays, dynamic price lines, and container resize observation.
 *
 * 3. Elements in the file:
 *    - CHART_TYPES: Array of supported chart type identifiers and display labels.
 *    - QuantChart: Central chart controller class.
 *
 * 4. Final output of the file:
 *    - Exported QuantChart class and CHART_TYPES constant for application orchestrators.
 */

import { api, fmtPrice, fmtTime, esc } from "./api.js";
import { heikinAshi } from "../lib/series.js";
import { DrawingLayer } from "./drawings.js";
import { BY_ID, compute } from "../lib/indicators.js";

const LW = window.LightweightCharts;

export const CHART_TYPES = [
  { id: "candles", label: "Candlestick" },
  { id: "heikin", label: "Heikin Ashi" },
  { id: "line", label: "Line" },
  { id: "area", label: "Area" },
];

const ICON = {
  gear: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/></svg>',
  eye: '<svg viewBox="0 0 24 24"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
};

let uidSeq = 0;
/**
 * 1. The use of function:
 *    Generates a unique string identifier for indicator instances.
 *
 * 2. How does the specific function work:
 *    Combines base-36 timestamp with incremental counter.
 *
 * 3. Concepts used in the function:
 *    UID generation, base-36 radix encoding.
 *
 * 4. Places where this function is imported and used:
 *    Used by QuantChart.addIndicator and callers.
 *
 * 5. Final output of the function, before and after:
 *    Before: None. After: Unique alphanumeric string.
 */
export const newUid = () => `i${Date.now().toString(36)}${(uidSeq++).toString(36)}`;

/**
 * 1. The use of function:
 *    Formats numeric indicator arrays into Lightweight Charts line series records with gaps.
 *
 * 2. How does the specific function work:
 *    Iterates through values, replaces NaNs with transparent breaks, and aligns with timestamps.
 *
 * 3. Concepts used in the function:
 *    Timeseries gap handling, transparent color breaks.
 *
 * 4. Places where this function is imported and used:
 *    Used by QuantChart.renderIndicators for line series.
 *
 * 5. Final output of the function, before and after:
 *    Before: Array of floats. After: Array of { time, value, color } objects.
 */
function lineData(vals, breaks, timeAt, n) {
  const out = [];
  const next = new Array(vals.length);
  let nv = NaN;
  for (let i = vals.length - 1; i >= 0; i--) {
    if (Number.isFinite(vals[i])) nv = vals[i];
    next[i] = nv;
  }
  let started = false;
  for (let i = 0; i < vals.length; i++) {
    const v = vals[i], time = timeAt(i);
    if (!Number.isFinite(v)) {
      if (i >= n) continue;
      out.push(started && Number.isFinite(next[i]) ? { time, value: next[i], color: "rgba(0,0,0,0)" } : { time });
      continue;
    }
    started = true;
    const gapAhead = i + 1 < vals.length && (!Number.isFinite(vals[i + 1]) || breaks?.[i + 1]);
    out.push(gapAhead ? { time, value: v, color: "rgba(0,0,0,0)" } : { time, value: v });
  }
  return out;
}

/**
 * 1. The use of function:
 *    Formats numeric oscillator arrays into Lightweight Charts histogram records with directional colors.
 *
 * 2. How does the specific function work:
 *    Maps values and optional per-bar color array into histogram timeseries points.
 *
 * 3. Concepts used in the function:
 *    Histogram data binding, per-bar color styling.
 *
 * 4. Places where this function is imported and used:
 *    Used by QuantChart.renderIndicators for MACD histogram.
 *
 * 5. Final output of the function, before and after:
 *    Before: Array of values and color strings. After: Array of { time, value, color } points.
 */
function histData(vals, colors, timeAt, n) {
  const out = [];
  for (let i = 0; i < vals.length; i++) {
    const v = vals[i];
    if (i >= n && !Number.isFinite(v)) continue;
    if (!Number.isFinite(v)) {
      out.push({ time: timeAt(i) });
    } else {
      out.push(colors ? { time: timeAt(i), value: v, color: colors[i] } : { time: timeAt(i), value: v });
    }
  }
  return out;
}

/**
 * 1. The use of class:
 *    Primary chart controller managing canvas rendering, price series, volume overlays,
 *    synthetic transforms, trade markers, and price lines using Lightweight Charts v5.
 *
 * 2. What the class contains:
 *    - container: HTML DOM element mounting the chart.
 *    - chart: Lightweight Charts v5 chart instance.
 *    - main: Primary price series (Candlestick, Line, or Area).
 *    - volume: Volume histogram sub-series.
 *    - symbol: Currently selected instrument symbol (e.g. NSE:NIFTY50).
 *    - timeframe: Active interval timeframe (e.g. 5m).
 *    - chartType: Active display mode (candles, heikin, line, area).
 *    - rawCandles: Immutable cache of downloaded OHLCV bars.
 *    - priceLines: Active price line handles for SL/TP and entry prices.
 *    - markersPlugin: Lightweight Charts series markers plugin instance.
 *
 * 3. Technologies used and why:
 *    TradingView Lightweight Charts v5 for 60-120 FPS hardware-accelerated canvas rendering
 *    without virtual DOM reconciliation overhead.
 *
 * 4. Key design and overall design of the class:
 *    Provides clean lifecycle encapsulation: setSymbol, setTimeframe, setChartType,
 *    loadCandles, setMarkers, addPriceLine, clearPriceLines, and syncResize.
 */
export class QuantChart {
  /**
   * 1. The use of function:
   *    Constructs and initializes the QuantChart instance inside target DOM element.
   *
   * 2. How does the specific function work:
   *    Stores configuration options, instantiates Lightweight Charts with dark theme tokens,
   *    creates the main candlestick and volume series, and binds resize observer.
   *
   * 3. Concepts used in the function:
   *    Constructor initialization, canvas container binding, theme configuration.
   *
   * 4. Places where this function is imported and used:
   *    Instantiated by apps/web/js/app.js during workstation bootstrap.
   *
   * 5. Final output of the function, before and after:
   *    Before: Container element. After: Fully initialized QuantChart instance with mounted canvas.
   */
  constructor(container, options = {}) {
    if (!container) throw new Error("QuantChart requires a valid DOM container");
    this.container = container;
    this.symbol = options.symbol || "NSE:NIFTY50";
    this.timeframe = options.timeframe || "5m";
    this.chartType = options.chartType || "candles";
    this.rawCandles = [];
    this.priceLines = [];
    this.tradeHighlightLines = [];
    this.markersPlugin = null;
    this.onSymbolChange = options.onSymbolChange || null;
    this.onTimeframeChange = options.onTimeframeChange || null;
    this.onOpenIndicatorSettings = options.onOpenIndicatorSettings || null;

    this.indicators = options.indicators || [
      { uid: "ema-9", id: "ema", params: { length: 9, source: "close" }, colors: { value: "#2962ff" }, hidden: false },
      { uid: "ema-21", id: "ema", params: { length: 21, source: "close" }, colors: { value: "#e91e63" }, hidden: false },
      { uid: "rsi-14", id: "rsi", params: { length: 14, source: "close" }, colors: { value: "#7e57c2" }, hidden: false },
    ];
    this.indSeries = new Map();
    this.indResults = {};
    this.indicatorMarkers = [];
    this.extraMarkers = [];
    this.clickListeners = [];

    this.initChart();
  }

  /**
   * 1. The use of function:
   *    Initializes the Lightweight Charts instance and attaches the main and volume series.
   *
   * 2. How does the specific function work:
   *    Calls LW.createChart with TradingView dark theme parameters, custom IST time formatters,
   *    and creates the initial candlestick and volume series.
   *
   * 3. Concepts used in the function:
   *    Lightweight Charts v5 factory, dark theme styling, price and volume scale decoupling.
   *
   * 4. Places where this function is imported and used:
   *    Called internally by QuantChart constructor.
   *
   * 5. Final output of the function, before and after:
   *    Before: Empty container. After: Rendered TradingView grid with main and volume series.
   */
  initChart() {
    this.chart = LW.createChart(this.container, {
      autoSize: true,
      layout: {
        background: { type: "solid", color: "#131722" },
        textColor: "#d1d4dc",
        fontSize: 11,
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      },
      grid: {
        vertLines: { color: "#1e222d" },
        horzLines: { color: "#1e222d" },
      },
      crosshair: {
        mode: LW.CrosshairMode.Normal,
        vertLine: {
          color: "rgba(117, 134, 150, 0.5)",
          width: 1,
          style: 3,
        },
        horzLine: {
          color: "rgba(117, 134, 150, 0.5)",
          width: 1,
          style: 3,
        },
      },
      rightPriceScale: {
        borderColor: "#2a2e39",
        scaleMargins: { top: 0.1, bottom: 0.2 },
      },
      timeScale: {
        borderColor: "#2a2e39",
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time) => fmtTime(time, "shortTime"),
      },
      localization: {
        priceFormatter: (p) => fmtPrice(p),
        timeFormatter: (t) => fmtTime(t, "datetime"),
      },
    });

    this.createMainSeries();
    this.createVolumeSeries();

    this.legendEl = this.container.querySelector(".legend");
    if (!this.legendEl) {
      this.legendEl = document.createElement("div");
      this.legendEl.className = "legend";
      this.legendEl.id = "chartLegend";
      this.container.appendChild(this.legendEl);
    }
    this.bindLegendEvents();

    this.drawings = new DrawingLayer(this);
    this.drawings.mount(this.container);

    this.chart.subscribeCrosshairMove((p) => {
      this.drawings?.onCrosshair(p);
      const i =
        p.logical != null && p.point
          ? Math.max(0, Math.min(this.rawCandles.length - 1, Math.round(p.logical)))
          : null;
      this.updateLegend(i);
    });
    this.chart.subscribeClick((p) => {
      this.drawings?.onClick(p);
      this.clickListeners.forEach((cb) => {
        try {
          cb(p);
        } catch (err) {
          console.warn("[QuantChart] Click listener error:", err);
        }
      });
    });
    this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => this.drawings?.drawOverlay());
    this.chart.timeScale().subscribeVisibleTimeRangeChange(() => this.drawings?.drawOverlay());

    const banner = document.getElementById("syntheticBanner");
    if (banner) {
      if (this.chartType === "heikin") {
        banner.classList.remove("hidden");
      } else {
        banner.classList.add("hidden");
      }
    }

    // Resize observer for container responsiveness
    if (window.ResizeObserver) {
      this.resizeObserver = new ResizeObserver(() => this.syncResize());
      this.resizeObserver.observe(this.container);
    }
  }

  /**
   * 1. The use of function:
   *    Constructs the primary price series based on current chartType (Candlestick, Line, or Area).
   *
   * 2. How does the specific function work:
   *    Removes existing main series if present, then instantiates the corresponding LW series type
   *    with canonical up/down colors (#089981 / #f23645).
   *
   * 3. Concepts used in the function:
   *    Dynamic series replacement, series lifecycle management.
   *
   * 4. Places where this function is imported and used:
   *    Called by initChart and setChartType.
   *
   * 5. Final output of the function, before and after:
   *    Before: Previous or no series. After: this.main bound to new series instance.
   */
  createMainSeries() {
    if (this.main) {
      this.clearPriceLines();
      this.chart.removeSeries(this.main);
      this.main = null;
      this.markersPlugin = null;
    }

    const up = "#089981";
    const down = "#f23645";
    const accent = "#2962ff";

    if (this.chartType === "line") {
      this.main = this.chart.addSeries(LW.LineSeries, {
        color: accent,
        lineWidth: 2,
        priceLineVisible: true,
        lastValueVisible: true,
      });
    } else if (this.chartType === "area") {
      this.main = this.chart.addSeries(LW.AreaSeries, {
        lineColor: accent,
        topColor: "rgba(41, 98, 255, 0.35)",
        bottomColor: "rgba(41, 98, 255, 0.02)",
        lineWidth: 2,
        priceLineVisible: true,
        lastValueVisible: true,
      });
    } else {
      // Candlesticks (default and Heikin Ashi)
      this.main = this.chart.addSeries(LW.CandlestickSeries, {
        upColor: up,
        downColor: down,
        borderVisible: false,
        wickUpColor: up,
        wickDownColor: down,
        priceLineVisible: true,
        lastValueVisible: true,
      });
    }

    if (LW.createSeriesMarkers && typeof LW.createSeriesMarkers === "function") {
      try {
        this.markersPlugin = LW.createSeriesMarkers(this.main, []);
      } catch {
        this.markersPlugin = null;
      }
    }
  }

  /**
   * 1. The use of function:
   *    Constructs the volume histogram sub-series on a separate overlay scale margin.
   *
   * 2. How does the specific function work:
   *    Creates an LW.HistogramSeries assigned to independent priceScaleId 'volume'
   *    with scaleMargins configured to occupy the lower 18% of the chart.
   *
   * 3. Concepts used in the function:
   *    Independent price scale overlay, volume histogram rendering.
   *
   * 4. Places where this function is imported and used:
   *    Called by initChart during initialization.
   *
   * 5. Final output of the function, before and after:
   *    Before: No volume series. After: this.volume created and positioned at bottom overlay.
   */
  createVolumeSeries() {
    if (this.volume) {
      this.chart.removeSeries(this.volume);
      this.volume = null;
    }

    this.volume = this.chart.addSeries(LW.HistogramSeries, {
      priceScaleId: "volume",
      priceFormat: { type: "volume" },
      priceLineVisible: false,
      lastValueVisible: false,
    });

    this.chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });
  }

  /**
   * 1. The use of function:
   *    Sets the active instrument symbol and triggers candle reloading.
   *
   * 2. How does the specific function work:
   *    Updates this.symbol and executes loadCandles().
   *
   * 3. Concepts used in the function:
   *    Symbol state transition, data pipeline trigger.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by symbol picker buttons and watchlist items.
   *
   * 5. Final output of the function, before and after:
   *    Before: Previous symbol. After: Chart reloaded with candles for new symbol.
   */
  async setSymbol(symbol) {
    if (!symbol || symbol === this.symbol) return;
    this.symbol = symbol;
    if (typeof this.onSymbolChange === "function") {
      this.onSymbolChange(symbol);
    }
    await this.loadCandles();
    if (this.drawings) {
      await this.drawings.loadDrawingsFromBackend(symbol);
    }
  }

  /**
   * 1. The use of function:
   *    Sets the active timeframe resolution and triggers candle reloading.
   *
   * 2. How does the specific function work:
   *    Updates this.timeframe and executes loadCandles().
   *
   * 3. Concepts used in the function:
   *    Multi-timeframe resolution switching.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by topbar timeframe buttons (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d).
   *
   * 5. Final output of the function, before and after:
   *    Before: Old timeframe. After: Chart reloaded with bars at new timeframe.
   */
  async setTimeframe(tf) {
    if (!tf || tf === this.timeframe) return;
    this.timeframe = tf;
    if (typeof this.onTimeframeChange === "function") {
      this.onTimeframeChange(tf);
    }
    await this.loadCandles();
  }

  /**
   * 1. The use of function:
   *    Switches the chart display mode (candles, heikin, line, area).
   *
   * 2. How does the specific function work:
   *    Updates this.chartType, toggles synthetic transform warning banner if heikin,
   *    recreates main series, and re-renders cached candles without re-fetching from API.
   *
   * 3. Concepts used in the function:
   *    Client-side series transformation, advisory banner toggling.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by #chartType select dropdown in topbar.
   *
   * 5. Final output of the function, before and after:
   *    Before: Previous display style. After: Newly styled series rendered on canvas.
   */
  setChartType(type) {
    if (!type || type === this.chartType) return;
    this.chartType = type;

    // Toggle synthetic advisory banner
    const banner = document.getElementById("syntheticBanner");
    if (banner) {
      if (type === "heikin") {
        banner.classList.remove("hidden");
      } else {
        banner.classList.add("hidden");
      }
    }

    this.createMainSeries();
    this.renderCachedData();
    this.renderIndicators();
    this.updateLegend();
  }

  /**
   * 1. The use of function:
   *    Fetches candles from FastAPI /api/v1/market/candles or /api/v1/options/candles and renders them.
   *
   * 2. How does the specific function work:
   *    - Queries appropriate endpoint based on symbol format.
   *    - Caches returned candles in this.rawCandles.
   *    - Formats candles according to active chartType (e.g. calculates Heikin Ashi).
   *    - Feeds main and volume series via series.setData().
   *    - Renders active indicator overlays and sub-panes.
   *    - Calls timeScale().fitContent() to display full series cleanly.
   *
   * 3. Concepts used in the function:
   *    Data ingestion, point-in-time candle caching, client-side transformation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked during initial bootstrap, symbol changes, and interval changes.
   *
   * 5. Final output of the function, before and after:
   *    Before: Previous candles. After: Updated series rendered on chart.
   */
  async loadCandles() {
    try {
      let resp;
      if (this.symbol.startsWith("OPT-") || this.symbol.startsWith("NIFTY_20") || /NIFTY.*[0-9]+.*[CP]E/i.test(this.symbol)) {
        resp = await api.getOptionCandles(this.symbol, this.timeframe, 5000);
      } else {
        resp = await api.getCandles(this.symbol, this.timeframe, 5000);
      }

      this.rawCandles = resp?.candles || [];
      this.renderCachedData();
      this.renderIndicators();
      this.updateLegend();
      if (this.rawCandles.length > 0) {
        this.chart.timeScale().fitContent();
      }
      if (this.drawings) {
        this.drawings.syncResize();
        this.drawings.update();
      }
    } catch (err) {
      console.error("[QuantChart] Failed to load candles:", err);
    }
  }

  /**
   * 1. The use of function:
   *    Registers an external callback function for chart click events.
   *
   * 2. How does the specific function work:
   *    Appends callback function to this.clickListeners array if not already present.
   *
   * 3. Concepts used in the function:
   *    Event listener registration, observer pattern.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by QuantApp bar replay engine in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Callback not registered. After: Callback invoked on subsequent chart clicks.
   */
  addClickListener(cb) {
    if (typeof cb === "function" && !this.clickListeners.includes(cb)) {
      this.clickListeners.push(cb);
    }
  }

  /**
   * 1. The use of function:
   *    Unregisters an external chart click event listener.
   *
   * 2. How does the specific function work:
   *    Filters out the provided callback function from this.clickListeners.
   *
   * 3. Concepts used in the function:
   *    Event listener deregistration, memory leak prevention.
   *
   * 4. Places where this function is imported and used:
   *    Invoked when exiting replay mode or dismantling chart observers.
   *
   * 5. Final output of the function, before and after:
   *    Before: Callback active. After: Callback removed from active subscriber array.
   */
  removeClickListener(cb) {
    this.clickListeners = this.clickListeners.filter((fn) => fn !== cb);
  }

  /**
   * 1. The use of function:
   *    Explicitly assigns and renders an array of OHLCV candles without triggering network fetch.
   *
   * 2. How does the specific function work:
   *    Updates this.rawCandles, executes renderCachedData() to refresh main/volume series,
   *    re-evaluates active indicators via renderIndicators(), refreshes legend HUD, and updates drawings.
   *
   * 3. Concepts used in the function:
   *    In-memory candle updates, high-throughput simulation replay, indicator re-computation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by QuantApp bar replay engine in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Chart displays previous bar series. After: Chart immediately reflects updated candle slice.
   */
  setCandles(candles = [], fit = false) {
    this.rawCandles = candles || [];
    this.renderCachedData();
    this.renderIndicators();
    this.updateLegend();
    if (this.drawings) {
      this.drawings.syncResize();
      this.drawings.update();
    }
    if (fit && this.chart && this.rawCandles.length > 0) {
      this.chart.timeScale().fitContent();
    }
  }

  /**
   * 1. The use of function:
   *    Transforms and renders currently cached raw candles according to active chartType.
   *
   * 2. How does the specific function work:
   *    - Applies heikinAshi() transform if chartType === 'heikin'.
   *    - Extracts value points if chartType === 'line' or 'area'.
   *    - Feeds data to this.main and this.volume series.
   *
   * 3. Concepts used in the function:
   *    Data transformation, series data binding.
   *
   * 4. Places where this function is imported and used:
   *    Called internally by loadCandles and setChartType.
   *
   * 5. Final output of the function, before and after:
   *    Before: Stale canvas series. After: Canvas updated with transformed data.
   */
  renderCachedData() {
    if (!this.main || this.rawCandles.length === 0) return;

    let displayBars = this.rawCandles;
    if (this.chartType === "heikin") {
      displayBars = heikinAshi(this.rawCandles);
    }

    if (this.chartType === "line" || this.chartType === "area") {
      const lineData = displayBars.map((b) => ({
        time: b.time,
        value: b.close,
      }));
      this.main.setData(lineData);
    } else {
      const candleData = displayBars.map((b) => ({
        time: b.time,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      }));
      this.main.setData(candleData);
    }

    if (this.volume) {
      const volData = this.rawCandles.map((b) => ({
        time: b.time,
        value: b.volume || 0,
        color:
          b.close >= b.open
            ? "rgba(8, 153, 129, 0.45)"
            : "rgba(242, 54, 69, 0.45)",
      }));
      this.volume.setData(volData);
    }
  }

  /**
   * 1. The use of function:
   *    Sets entry/exit trade markers on the candlestick series.
   *
   * 2. How does the specific function work:
   *    Passes markers array to markersPlugin.setMarkers() or main.setMarkers().
   *    Markers are sorted chronologically by time ascending.
   *
   * 3. Concepts used in the function:
   *    Lightweight Charts marker overlay, temporal sorting.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Strategy Tester tear sheet when plotting backtest executions.
   *
   * 5. Final output of the function, before and after:
   *    Before: No markers or previous markers. After: Arrows plotted above/below execution bars.
   */
  setMarkers(markers = []) {
    this.extraMarkers = [...markers];
    this.syncAllMarkers();
  }

  /**
   * 1. The use of function:
   *    Merges trade markers with indicator structural swing markers (e.g. BOS/CHoCH) and renders them.
   *
   * 2. How does the specific function work:
   *    Combines extraMarkers and indicatorMarkers arrays, sorts chronologically by time ascending,
   *    and feeds to Lightweight Charts markers plugin.
   *
   * 3. Concepts used in the function:
   *    Marker collation, temporal sorting.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by setMarkers and renderIndicators.
   *
   * 5. Final output of the function, before and after:
   *    Before: Separate marker lists. After: Combined markers rendered on chart series.
   */
  syncAllMarkers() {
    const all = [...(this.extraMarkers || []), ...(this.indicatorMarkers || [])];
    all.sort((a, b) => a.time - b.time);
    if (this.markersPlugin && typeof this.markersPlugin.setMarkers === "function") {
      this.markersPlugin.setMarkers(all);
    } else if (this.main && typeof this.main.setMarkers === "function") {
      this.main.setMarkers(all);
    } else if (LW.createSeriesMarkers && this.main) {
      try {
        this.markersPlugin = LW.createSeriesMarkers(this.main, all);
      } catch (err) {
        console.warn("[QuantChart] Failed to create markers:", err);
      }
    }
  }

  /**
   * 1. The use of function:
   *    Pans and scrolls the chart viewport to center or focus around a specific UTC timestamp.
   *
   * 2. How does the specific function work:
   *    Computes logical bar index for the target UTC epoch seconds via logicalOf(utc).
   *    If valid logical index exists, sets the visible logical range to span 60 bars around the index.
   *    Falls back to timeScale().setVisibleRange() if logical coordinate conversion is unavailable.
   *
   * 3. Concepts used in the function:
   *    Time-scale viewport manipulation, logical bar indexing, coordinate navigation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Strategy Tester trade log row click to immediately focus on the trade entry candle.
   *
   * 5. Final output of the function, before and after:
   *    Before: Arbitrary viewport position. After: Chart scrolled and centered at target execution time.
   */
  scrollToTime(utc) {
    if (!this.chart || utc == null) return;
    const l = this.logicalOf(utc);
    if (l != null && Number.isFinite(l)) {
      try {
        const from = Math.max(0, Math.floor(l - 25));
        const to = Math.max(from + 50, Math.ceil(l + 35));
        this.chart.timeScale().setVisibleLogicalRange({ from, to });
        return;
      } catch {
        /* fallback to time range */
      }
    }
    try {
      this.chart.timeScale().setVisibleRange({ from: utc - 3600, to: utc + 7200 });
    } catch {
      /* ignore */
    }
  }

  /**
   * 1. The use of function:
   *    Highlights a specific backtested trade on the chart with visual price lines and scrolling.
   *
   * 2. How does the specific function work:
   *    Clears any prior temporary trade highlight lines. Creates an entry price line (green dashed)
   *    and exit price line (red dashed) on the main series, and scrolls viewport to trade entry_time.
   *
   * 3. Concepts used in the function:
   *    Interactive trade audit, on-chart price level demarcation, synchronized scrolling.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Strategy Tester audit trade log row click in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Standard chart view. After: Chart centered at entry bar with entry/exit price levels indicated.
   */
  highlightTrade(trade) {
    if (!trade || !this.main) return;
    if (this.tradeHighlightLines) {
      for (const line of this.tradeHighlightLines) {
        try {
          this.main.removePriceLine(line);
        } catch {
          /* ignore */
        }
      }
    }
    this.tradeHighlightLines = [];

    if (trade.entry_time) {
      this.scrollToTime(trade.entry_time);
    }

    if (trade.entry_price != null && Number.isFinite(trade.entry_price)) {
      try {
        const entryLine = this.main.createPriceLine({
          price: trade.entry_price,
          color: "#26a69a",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `AUDIT ENTRY: ₹${trade.entry_price.toFixed(2)}`,
        });
        this.tradeHighlightLines.push(entryLine);
      } catch {
        /* ignore */
      }
    }

    if (trade.exit_price != null && Number.isFinite(trade.exit_price)) {
      try {
        const exitLine = this.main.createPriceLine({
          price: trade.exit_price,
          color: "#ef5350",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `AUDIT EXIT: ₹${trade.exit_price.toFixed(2)} (${trade.exit_reason || "EXIT"})`,
        });
        this.tradeHighlightLines.push(exitLine);
      } catch {
        /* ignore */
      }
    }
  }

  /**
   * 1. The use of function:
   *    Adds an on-chart horizontal price line for Entry, Stop-Loss, or Take-Profit levels.
   *
   * 2. How does the specific function work:
   *    Calls this.main.createPriceLine with price level, color, title, and styling options.
   *    Stores handle in this.priceLines and returns it.
   *
   * 3. Concepts used in the function:
   *    Chart price line overlay, order level visualization.
   *
   * 4. Places where this function is imported and used:
   *    Invoked immediately following paper order placement from Option Chain or manual orders.
   *
   * 5. Final output of the function, before and after:
   *    Before: Price line absent. After: Horizontal line plotted at price coordinate.
   */
  addPriceLine({ price, color = "#2962ff", title = "", lineStyle = 2, lineWidth = 1 }) {
    if (!this.main || price == null || !Number.isFinite(price)) return null;

    const handle = this.main.createPriceLine({
      price,
      color,
      lineWidth: lineWidth || 1,
      lineStyle, // 0 = Solid, 1 = Dotted, 2 = Dashed
      axisLabelVisible: true,
      title: title || "",
    });

    this.priceLines.push(handle);
    return handle;
  }

  /**
   * 1. The use of function:
   *    Removes all active price lines from the chart canvas.
   *
   * 2. How does the specific function work:
   *    Iterates over this.priceLines and calls this.main.removePriceLine(handle).
   *
   * 3. Concepts used in the function:
   *    Price line cleanup, memory management.
   *
   * 4. Places where this function is imported and used:
   *    Invoked upon symbol change, series recreation, or position closure.
   *
   * 5. Final output of the function, before and after:
   *    Before: Active price lines on canvas. After: All price lines removed.
   */
  clearPriceLines() {
    if (!this.main) {
      this.priceLines = [];
      this.tradeHighlightLines = [];
      return;
    }
    for (const handle of this.priceLines) {
      try {
        this.main.removePriceLine(handle);
      } catch {
        /* ignore */
      }
    }
    this.priceLines = [];
    if (this.tradeHighlightLines) {
      for (const handle of this.tradeHighlightLines) {
        try {
          this.main.removePriceLine(handle);
        } catch {
          /* ignore */
        }
      }
      this.tradeHighlightLines = [];
    }
  }

  /**
   * 1. The use of function:
   *    Synchronizes the chart dimensions with the container's client dimensions.
   *
   * 2. How does the specific function work:
   *    Measures container clientWidth and clientHeight and calls chart.resize(w, h).
   *
   * 3. Concepts used in the function:
   *    Canvas resize synchronization, responsive layout.
   *
   * 4. Places where this function is imported and used:
   *    Invoked when bottom dock expands/collapses or window resizes.
   *
   * 5. Final output of the function, before and after:
   *    Before: Mismatched canvas resolution. After: Canvas resized pixel-perfectly to container.
   */
  syncResize() {
    if (!this.chart || !this.container) return;
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    if (w > 0 && h > 0) {
      this.chart.resize(w, h);
    }
    if (this.drawings) {
      this.drawings.syncResize();
    }
  }

  /**
   * 1. The use of function:
   *    Applies visual color theme (light or dark) dynamically to Lightweight Charts options.
   *
   * 2. How does the specific function work:
   *    Updates chart background color, text color, and grid line colors via chart.applyOptions,
   *    refreshes legend HUD text colors, and triggers drawing overlay repaint.
   *
   * 3. Concepts used in the function:
   *    Chart theming, dynamic styling, canvas color synchronization.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by theme toggle handler in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Chart styled with previous theme. After: Chart options updated to match dark or light theme.
   */
  setTheme(theme) {
    this.theme = theme;
    const isLight = theme === "light";
    const bg = isLight ? "#ffffff" : "#131722";
    const textColor = isLight ? "#131722" : "#d1d4dc";
    const gridColor = isLight ? "#f0f3fa" : "#1e222d";

    if (this.chart) {
      try {
        this.chart.applyOptions({
          layout: {
            background: { type: "solid", color: bg },
            textColor: textColor,
          },
          grid: {
            vertLines: { color: gridColor },
            horzLines: { color: gridColor },
          },
        });
      } catch {
        /* ignore */
      }
    }
    this.updateLegend();
    if (this.drawings) {
      this.drawings.update();
    }
  }

  /**
   * 1. The use of function:
   *    Calculates the fractional logical index corresponding to a given UTC epoch timestamp.
   *
   * 2. How does the specific function work:
   *    Extracts time series from cached rawCandles, applies binary search between candle timestamps,
   *    and linearly interpolates the logical coordinate index.
   *
   * 3. Concepts used in the function:
   *    Binary search, linear interpolation, temporal coordinate mapping.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by DrawingLayer for timeToX projections and bar counting in measurement tools.
   *
   * 5. Final output of the function, before and after:
   *    Before: UTC epoch seconds. After: Fractional logical index float (or null if empty).
   */
  logicalOf(utc) {
    const T = this.rawCandles.map((c) => c.time);
    const n = T.length;
    if (!n) return null;
    const step = n > 1 ? (T[1] - T[0]) || 300 : 300;
    if (utc <= T[0]) return (utc - T[0]) / step;
    if (utc >= T[n - 1]) return n - 1 + (utc - T[n - 1]) / step;
    let lo = 0;
    let hi = n - 1;
    while (hi - lo > 1) {
      const m = (lo + hi) >> 1;
      if (T[m] <= utc) lo = m;
      else hi = m;
    }
    return lo + (utc - T[lo]) / ((T[hi] - T[lo]) || 1);
  }

  /**
   * 1. The use of function:
   *    Converts a fractional logical index back into a UTC epoch second timestamp.
   *
   * 2. How does the specific function work:
   *    Interpolates or extrapolates along the rawCandles timestamp series using the candle step.
   *
   * 3. Concepts used in the function:
   *    Inverse logical interpolation, temporal projection.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by pointAtXY to resolve mouse pixel coordinates to time.
   *
   * 5. Final output of the function, before and after:
   *    Before: Logical index float. After: Integer UTC epoch seconds (or null if empty).
   */
  timeOfLogical(l) {
    const T = this.rawCandles.map((c) => c.time);
    const n = T.length;
    if (!n) return null;
    const step = n > 1 ? (T[1] - T[0]) || 300 : 300;
    if (l <= 0) return Math.round(T[0] + l * step);
    if (l >= n - 1) return Math.round(T[n - 1] + (l - (n - 1)) * step);
    const i = Math.floor(l);
    return Math.round(T[i] + (l - i) * (T[i + 1] - T[i]));
  }

  /**
   * 1. The use of function:
   *    Projects a UTC epoch timestamp to a canvas horizontal pixel X coordinate.
   *
   * 2. How does the specific function work:
   *    Translates UTC time to logical coordinate via logicalOf() and queries chart.timeScale().logicalToCoordinate().
   *
   * 3. Concepts used in the function:
   *    Lightweight Charts time scale coordinate conversion.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by DrawingLayer.x() for rendering drawing vectors.
   *
   * 5. Final output of the function, before and after:
   *    Before: UTC timestamp. After: Horizontal pixel coordinate number (or null).
   */
  timeToX(utc) {
    const l = this.logicalOf(utc);
    return l == null ? null : this.chart.timeScale().logicalToCoordinate(l);
  }

  /**
   * 1. The use of function:
   *    Projects a numerical price level to a canvas vertical pixel Y coordinate.
   *
   * 2. How does the specific function work:
   *    Queries this.main.priceToCoordinate(price).
   *
   * 3. Concepts used in the function:
   *    Price scale coordinate projection.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by DrawingLayer.y() for rendering drawing geometries.
   *
   * 5. Final output of the function, before and after:
   *    Before: Float price. After: Vertical pixel coordinate number (or null).
   */
  priceToY(p) {
    return this.main?.priceToCoordinate(p) ?? null;
  }

  /**
   * 1. The use of function:
   *    Converts a vertical canvas pixel coordinate back into a price level.
   *
   * 2. How does the specific function work:
   *    Queries this.main.coordinateToPrice(y).
   *
   * 3. Concepts used in the function:
   *    Inverse price coordinate mapping.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by pointAtXY when capturing anchor point clicks.
   *
   * 5. Final output of the function, before and after:
   *    Before: Vertical pixel coordinate. After: Numerical price level (or null).
   */
  coordinateToPrice(y) {
    return this.main?.coordinateToPrice(y) ?? null;
  }

  /**
   * 1. The use of function:
   *    Resolves canvas pixel coordinates (x, y) into a chart coordinate { time, price }.
   *
   * 2. How does the specific function work:
   *    Translates pixel X to logical bar index via timeScale().coordinateToLogical(x),
   *    resolves logical index to UTC timestamp via timeOfLogical(), and translates pixel Y
   *    to price via coordinateToPrice(y).
   *
   * 3. Concepts used in the function:
   *    Two-dimensional spatial-to-domain coordinate translation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by DrawingLayer.pointAt() when anchoring drawing vertices.
   *
   * 5. Final output of the function, before and after:
   *    Before: Pixel coordinates (x, y). After: Point object { time: UtcEpochSec, price: number } or null.
   */
  pointAtXY(x, y) {
    if (!this.chart || !this.main) return null;
    const logical = this.chart.timeScale().coordinateToLogical(x);
    if (logical == null) return null;
    const time = this.timeOfLogical(logical);
    const price = this.coordinateToPrice(y);
    if (time == null || price == null) return null;
    return { time, price };
  }

  /**
   * 1. The use of function:
   *    Deletes the currently selected drawing item from the chart.
   *
   * 2. How does the specific function work:
   *    Delegates deletion to this.drawings.deleteSelectedDrawing().
   *
   * 3. Concepts used in the function:
   *    Drawing deletion proxy.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by QuantApp when Delete/Backspace key is pressed or toolbar trash clicked.
   *
   * 5. Final output of the function, before and after:
   *    Before: Selected drawing item. After: Drawing item deleted and purged from backend.
   */
  deleteSelectedDrawing() {
    return this.drawings?.deleteSelectedDrawing() ?? false;
  }

  /**
   * 1. The use of function:
   *    Clears all drawing annotations on the current instrument symbol.
   *
   * 2. How does the specific function work:
   *    Delegates clearing to this.drawings.clearDrawings().
   *
   * 3. Concepts used in the function:
   *    Bulk drawing purge proxy.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by QuantApp when toolbar clear button is clicked.
   *
   * 5. Final output of the function, before and after:
   *    Before: Symbol drawings present. After: All drawings removed and purged from backend.
   */
  clearDrawings() {
    return this.drawings?.clearDrawings();
  }

  /**
   * 1. The use of function:
   *    Adds an indicator configuration to the active chart and triggers re-rendering.
   *
   * 2. How does the specific function work:
   *    Allocates a unique UID via newUid(), appends indicator configuration object to this.indicators,
   *    calls renderIndicators() to calculate and draw series, and updates legend.
   *
   * 3. Concepts used in the function:
   *    Dynamic indicator composition, declarative configuration state.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Indicator Catalog Dialog and workstation initialization.
   *
   * 5. Final output of the function, before and after:
   *    Before: Indicator absent. After: Indicator appended and rendered; returns unique string uid.
   */
  addIndicator(id, params = {}, colors = {}) {
    const uid = newUid();
    const ind = { uid, id, params, colors, hidden: false };
    this.indicators.push(ind);
    this.renderIndicators();
    this.updateLegend();
    return uid;
  }

  /**
   * 1. The use of function:
   *    Removes an indicator series and associated sub-pane from the chart.
   *
   * 2. How does the specific function work:
   *    Filters out indicator with matching uid, removes its series from Lightweight Charts,
   *    re-renders remaining indicators and panes, and refreshes legend badges.
   *
   * 3. Concepts used in the function:
   *    Series lifecycle management, sub-pane garbage collection.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by indicator legend 'X' micro-button.
   *
   * 5. Final output of the function, before and after:
   *    Before: Indicator present. After: Indicator removed from canvas and state.
   */
  removeIndicator(uid) {
    this.indicators = this.indicators.filter((x) => x.uid !== uid);
    const seriesList = this.indSeries.get(uid);
    if (seriesList) {
      for (const s of seriesList) {
        try {
          this.chart.removeSeries(s);
        } catch {
          /* ignore */
        }
      }
      this.indSeries.delete(uid);
    }
    this.renderIndicators();
    this.updateLegend();
  }

  /**
   * 1. The use of function:
   *    Updates calculation parameters and color styling for an active indicator.
   *
   * 2. How does the specific function work:
   *    Finds target indicator by uid, merges params and colors dictionaries,
   *    recalculates series via renderIndicators(), and updates legend display.
   *
   * 3. Concepts used in the function:
   *    Dynamic parameter mutation, non-destructive canvas refresh.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Indicator Settings Modal upon saving changes.
   *
   * 5. Final output of the function, before and after:
   *    Before: Old parameters. After: Recalculated indicator plotted on chart canvas.
   */
  updateIndicator(uid, params = {}, colors = {}) {
    const ind = this.indicators.find((x) => x.uid === uid);
    if (!ind) return;
    ind.params = { ...ind.params, ...params };
    ind.colors = { ...ind.colors, ...colors };
    this.renderIndicators();
    this.updateLegend();
  }

  /**
   * 1. The use of function:
   *    Toggles visibility of an indicator series without removing its configuration.
   *
   * 2. How does the specific function work:
   *    Inverts ind.hidden boolean, triggers renderIndicators() to add/remove series,
   *    and updates legend badge styling (dimming opacity when hidden).
   *
   * 3. Concepts used in the function:
   *    Visibility toggling, state preservation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by indicator legend Eye micro-button.
   *
   * 5. Final output of the function, before and after:
   *    Before: Visible/hidden state. After: Inverted visibility state.
   */
  toggleIndicatorVisibility(uid) {
    const ind = this.indicators.find((x) => x.uid === uid);
    if (!ind) return;
    ind.hidden = !ind.hidden;
    this.renderIndicators();
    this.updateLegend();
  }

  /**
   * 1. The use of function:
   *    Returns shallow copy of active indicator configuration array.
   *
   * 2. How does the specific function work:
   *    Returns this.indicators array clone.
   *
   * 3. Concepts used in the function:
   *    Immutable state getter.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by workstation state serializers and diagnostics.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Array of indicator instance objects.
   */
  getIndicators() {
    return [...this.indicators];
  }

  /**
   * 1. The use of function:
   *    Evaluates indicator algorithm over chart candle bars using client library or error fallback.
   *
   * 2. How does the specific function work:
   *    Resolves indicator definition from BY_ID registry, invokes compute(id, bars, params),
   *    and returns computed series dictionary or error envelope.
   *
   * 3. Concepts used in the function:
   *    Pure mathematical calculation, error isolation.
   *
   * 4. Places where this function is imported and used:
   *    Called internally by renderIndicators().
   *
   * 5. Final output of the function, before and after:
   *    Before: Raw candle bars. After: Computed indicator lines/markers dictionary.
   */
  computeIndicator(ind, bars) {
    const def = BY_ID[ind.id];
    if (!def) return { error: `Indicator '${ind.id}' not found in registry.` };
    try {
      return compute(ind.id, bars, ind.params || {});
    } catch (err) {
      return { error: err.message };
    }
  }

  /**
   * 1. The use of function:
   *    Constructs human-readable parameter badge label (e.g. '9', '21', '14', '12, 26, 9').
   *
   * 2. How does the specific function work:
   *    Extracts input defaults and overrides from indicator definition and configuration,
   *    joining values with commas.
   *
   * 3. Concepts used in the function:
   *    Parameter label formatting.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by updateLegend().
   *
   * 5. Final output of the function, before and after:
   *    Before: Indicator instance. After: Formatted parameter string.
   */
  indicatorParamsLabel(ind) {
    const def = BY_ID[ind.id];
    if (!def) return "";
    const nums = (def.inputs || [])
      .filter((x) => x.type !== "source")
      .map((x) => {
        const v = ind.params?.[x.key] ?? x.default;
        if (x.type === "time") {
          return v ? new Date(v * 1000).toLocaleDateString() : "";
        }
        return v;
      })
      .filter((v) => v !== undefined && v !== "")
      .join(", ");
    return nums;
  }

  /**
   * 1. The use of function:
   *    Renders all active technical indicator overlays and sub-panes in Lightweight Charts.
   *
   * 2. How does the specific function work:
   *    - Cleans up previously registered indicator series.
   *    - Purges sub-panes back to primary pane 0.
   *    - Calculates values for each indicator using computeIndicator().
   *    - Allocates overlay series on pane 0 or creates sub-panes for oscillators (RSI, MACD, ATR).
   *    - Formats line series and multi-color histogram bars (green above 0, red below 0).
   *    - Adds reference levels (e.g. 70/30 on RSI).
   *    - Synchronizes multi-pane stretch factors (1 for price pane, 0.28 for sub-panes).
   *    - Merges structural markers (BOS/CHoCH) with trade markers via syncAllMarkers().
   *
   * 3. Concepts used in the function:
   *    Multi-pane chart layout, time-scale synchronization, histogram & line series rendering.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by loadCandles, setChartType, addIndicator, removeIndicator, and updateIndicator.
   *
   * 5. Final output of the function, before and after:
   *    Before: Unsynced or stale canvas series. After: Active indicators and sub-panes rendered at 60 FPS.
   */
  renderIndicators() {
    // Clear old indicator series
    for (const list of this.indSeries.values()) {
      for (const s of list) {
        try {
          this.chart.removeSeries(s);
        } catch {
          /* ignore */
        }
      }
    }
    this.indSeries.clear();

    // Remove existing sub-panes (keep only main pane 0)
    if (this.chart.panes && typeof this.chart.panes === "function") {
      while (this.chart.panes().length > 1) {
        try {
          this.chart.removePane(this.chart.panes().length - 1);
        } catch {
          break;
        }
      }
    }

    this.indResults = {};
    this.indicatorMarkers = [];
    const bars = this.rawCandles;
    const n = bars.length;
    if (!n) return;

    const step = n > 1 ? (bars[1].time - bars[0].time) || 300 : 300;
    const timeAt = (i) => (i < n ? bars[i].time : bars[n - 1].time + (i - n + 1) * step);

    let paneIdx = 0;
    const paneOf = {};

    for (const ind of this.indicators) {
      const def = BY_ID[ind.id];
      if (!def) continue;

      let res;
      try {
        res = this.computeIndicator(ind, bars);
      } catch (err) {
        res = { error: err.message };
      }
      this.indResults[ind.uid] = res;

      if (ind.hidden) continue;

      if (res.markers && Array.isArray(res.markers)) {
        this.indicatorMarkers.push(...res.markers);
      }

      const outs = (def.outputs || []).filter((o) => Array.isArray(res[o.key]));
      if (!outs.length) continue;

      const pane = def.overlay ? 0 : ++paneIdx;
      paneOf[ind.uid] = pane;
      const list = [];

      for (const out of outs) {
        const color = ind.colors?.[out.key] || out.color || "#2962ff";
        const opts = {
          color,
          priceLineVisible: false,
          lastValueVisible: pane > 0,
          crosshairMarkerVisible: false,
          title: "",
        };

        let s;
        if (out.kind === "histogram") {
          s = this.chart.addSeries(LW.HistogramSeries, opts, pane);
          const vals = res[out.key];
          s.setData(histData(vals, res.colors, timeAt, n));
        } else {
          const lineOpts = {
            ...opts,
            lineWidth: out.lineWidth || 1,
          };
          if (out.dots) {
            lineOpts.lineVisible = false;
            lineOpts.pointMarkersVisible = true;
            lineOpts.pointMarkersRadius = 1.5;
          }
          s = this.chart.addSeries(LW.LineSeries, lineOpts, pane);
          const vals = res[out.key];
          s.setData(lineData(vals, res.breaks, timeAt, n));
        }
        list.push(s);
      }

      // Reference levels (e.g. 70 and 30 for RSI)
      if (!def.overlay && def.levels && list.length > 0) {
        for (const lv of def.levels) {
          try {
            list[0].createPriceLine({
              price: lv,
              color: "rgba(117, 134, 150, 0.4)",
              lineWidth: 1,
              lineStyle: LW.LineStyle?.Dashed ?? 2,
              axisLabelVisible: true,
              title: `${lv}`,
            });
          } catch {
            /* ignore */
          }
        }
      }

      this.indSeries.set(ind.uid, list);
    }

    // Stretch factors for multi-pane layout (main gets 1, subpanes get 0.28)
    if (this.chart.panes && typeof this.chart.panes === "function") {
      const panes = this.chart.panes();
      panes.forEach((p, i) => {
        if (typeof p.setStretchFactor === "function") {
          p.setStretchFactor(i === 0 ? 1 : 0.28);
        }
      });
    }

    // Update all markers (trade markers + structural indicator markers)
    this.syncAllMarkers();
  }

  /**
   * 1. The use of function:
   *    Attaches interactive click listeners on indicator legend micro-buttons.
   *
   * 2. How does the specific function work:
   *    Binds click delegation to legend element handling settings modal trigger,
   *    hide/show visibility toggle, and indicator removal.
   *
   * 3. Concepts used in the function:
   *    Event delegation, micro-action dispatching.
   *
   * 4. Places where this function is imported and used:
   *    Called by initChart().
   *
   * 5. Final output of the function, before and after:
   *    Before: Passive legend. After: Interactive buttons wired to chart actions.
   */
  bindLegendEvents() {
    if (!this.legendEl) return;
    this.legendEl.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-act]");
      if (!btn) return;
      e.stopPropagation();
      const act = btn.dataset.act;
      const row = btn.closest("[data-uid]");
      const uid = row?.dataset.uid;
      if (!uid) return;

      if (act === "remove") {
        this.removeIndicator(uid);
      } else if (act === "hide") {
        this.toggleIndicatorVisibility(uid);
      } else if (act === "settings") {
        const ind = this.indicators.find((x) => x.uid === uid);
        if (ind && typeof this.onOpenIndicatorSettings === "function") {
          this.onOpenIndicatorSettings(ind);
        }
      }
    });
  }

  /**
   * 1. The use of function:
   *    Updates top-left chart legend with current bar OHLC and active indicator value badges.
   *
   * 2. How does the specific function work:
   *    Extracts candle bar at logical index (defaults to latest bar), renders price change %,
   *    and iterates through active indicators rendering title, params, value coordinates,
   *    and interactive micro-buttons (settings gear, eye hide, remove X).
   *
   * 3. Concepts used in the function:
   *    DOM template rendering, crosshair tracking, indicator HUD visualization.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by crosshair move subscriber and renderIndicators().
   *
   * 5. Final output of the function, before and after:
   *    Before: Stale legend HTML. After: Live updated HUD reflecting cursor position.
   */
  updateLegend(index = null) {
    if (!this.legendEl) return;
    const n = this.rawCandles.length;
    const i = index != null ? index : n - 1;
    const b = n > 0 && i >= 0 && i < n ? this.rawCandles[i] : null;
    const prev = n > 1 && i > 0 && i < n ? this.rawCandles[i - 1] : null;
    const chg = b && prev ? ((b.close - prev.close) / prev.close) * 100 : null;
    const cls = chg == null ? "" : chg >= 0 ? "up" : "down";
    const name = `${this.symbol} · ${this.timeframe}`;

    let html = `<div class="row"><span class="title" style="color:var(--text);font-weight:600;">${esc(name)}</span>`;
    if (b) {
      const chgStr = chg != null ? (chg >= 0 ? "+" : "") + chg.toFixed(2) + "%" : "";
      html += `<span class="ohlc ${cls}"><span><b>O</b>${fmtPrice(b.open)}</span><span><b>H</b>${fmtPrice(b.high)}</span><span><b>L</b>${fmtPrice(b.low)}</span><span><b>C</b>${fmtPrice(b.close)}</span><span>${chgStr}</span></span>`;
    }
    html += `</div>`;

    for (const ind of this.indicators) {
      const def = BY_ID[ind.id];
      if (!def) continue;
      const res = this.indResults[ind.uid] || {};
      const params = this.indicatorParamsLabel(ind);
      const short = /\(([^)]+)\)$/.exec(def.name)?.[1].split(" / ")[0] || def.name;
      const label = params ? `${short} ${params}` : short;

      let vals = "";
      if (res.error) {
        vals = `<span class="down">${esc(res.error)}</span>`;
      } else if (def.outputs && b) {
        vals = def.outputs
          .map((o) => {
            const v = res[o.key]?.[i];
            const c = ind.colors?.[o.key] || o.color || "var(--text)";
            return Number.isFinite(v) ? `<span style="color:${c};margin-right:6px;">${fmtPrice(v)}</span>` : "";
          })
          .filter(Boolean)
          .join(" ");
      }

      const rowStyle = ind.hidden ? "opacity:0.45;" : "";
      html += `
        <div class="row ind" data-uid="${ind.uid}" style="${rowStyle}">
          <span class="name" style="cursor:pointer;" title="Click gear for settings">${esc(label)}</span>
          <span class="vals" style="margin-left:6px;">${vals}</span>
          <span class="acts">
            <button data-act="settings" title="Settings">${ICON.gear}</button>
            <button data-act="hide" title="Show / Hide">${ICON.eye}</button>
            <button data-act="remove" title="Remove">${ICON.x}</button>
          </span>
        </div>
      `;
    }

    this.legendEl.innerHTML = html;
  }

  /**
   * 1. The use of function:
   *    Destroys the chart instance, cancels animation frames, and disconnects DOM observers.
   *
   * 2. How does the specific function work:
   *    Disconnects the active ResizeObserver, cleans up indicator and drawing series,
   *    removes legend element, invokes chart.remove(), and nullifies pointers.
   *
   * 3. Concepts used in the function:
   *    Resource deallocation, DOM observer teardown, memory leak prevention.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by QuantApp during workstation teardown or container unmounting.
   *
   * 5. Final output of the function, before and after:
   *    Before: Active chart holding DOM and canvas resources. After: Cleanly released instance.
   */
  destroy() {
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
    if (this.drawings) {
      this.drawings.destroy();
      this.drawings = null;
    }
    for (const list of this.indSeries.values()) {
      for (const s of list) {
        try {
          this.chart?.removeSeries(s);
        } catch {
          /* ignore */
        }
      }
    }
    this.indSeries.clear();
    if (this.legendEl && this.legendEl.parentNode) {
      this.legendEl.parentNode.removeChild(this.legendEl);
      this.legendEl = null;
    }
    if (this.chart) {
      this.chart.remove();
      this.chart = null;
    }
  }
}
