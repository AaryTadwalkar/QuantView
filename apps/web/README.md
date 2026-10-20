# QuantView — Web Application (`apps/web`)

**Role:** Next.js 14+ Frontend Application  
**Architecture Reference:** `DOCS/QUANTVIEW_MASTER_SPEC.md` §3, `DOCS/QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md` §11  

---

## 1. Overview & UI Tiers

The web application provides the user interface for:
1. **Charting UX:** Interactive candlestick charts using Lightweight Charts wrapped in `LightweightChartsAdapter` with canonical `UtcEpochSec` timestamps and localized IST display.
2. **Option Chain View:** Live/historical strikes, Greeks (IV, Delta, Gamma, Theta, Vega), OI, and volume.
3. **Backtest Runner & Diagnostics:** Form for submitting `RunConfig`, monitoring progress, and reviewing backtest tear sheets.
4. **Paper Trading Terminal:** Account overview, open positions, order placement (market orders only for v1 per ADR-039), and live ledger event feed.

---

## 2. Boundary Rules

- `apps/web` communicates exclusively with `services/api` via REST (`/api/v1/*`) and WebSocket streams.
- It never touches raw data files, database connections, or background worker processes directly.
- All monetary values are rendered from integer paise.
- All timestamps from the server are in UTC epoch seconds (`UtcEpochSec`).
