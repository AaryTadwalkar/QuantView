# Progress

## What works
- Upstox REST historical candle fetcher (`fetch_historical.py`) — functional for NIFTY index.
- Incremental extension fetcher (`fetch_historical_extension.py`) — works but saves to separate file.
- `merge_extensions.py` — merges extension CSV into main (but overwrites raw; risky).
- Option chain snapshot collector — collects ~30s cadence snapshots; operational but unreliable (gaps, late starts).
- `data_status.py` — generates `data_status.md` audit report; uses business-day calendar (not exchange holidays).

## What's collected
- 1m NIFTY candles: 2022-01-03 to 2026-10-08 (~432,967 rows)
- Higher-TF NIFTY candles: 3m, 5m, 15m, 1h, 4h, 1d
- Option chain snapshots: 2026-01-20 to 2026-10-09 (78,535 files, 35 expiry folders)
- Live daily 1m candle CSVs: 57 files (2026-01-20 to at least 2026-06-08)

## What's left to build (Phase 0 gates)
- [ ] G1: NSE calendar — **next task**
- [ ] G2: Calendar-driven audit v2
- [ ] G3: Robust folder discovery (fix non-zero-padded names)
- [ ] G4: Timestamp semantics documentation + resampling parity
- [ ] G5: Expired option API access verification
- [ ] G6: Parquet conversion + checksummed backup
- [ ] G7: Causality test harness in CI
- [ ] G8: Reliable collector (heartbeat, reconnect, scheduling)

## Current status
Phase 0 — Data collection operational; all gates unmet; no application code started.

## Known issues
- 19k 1m candle row count discrepancy (reported vs. observed).
- 3 non-zero-padded expiry folders break parsers.
- Multiple utility scripts have hardcoded wrong paths.
- `pyarrow` missing from requirements — Parquet impossible.
- No backup of collected data.
- Volume=0, OI=0 in all NIFTY candles (undocumented).
- Option chain timezone not documented.
- Saturday erroneous rows in both candle and option chain data.
