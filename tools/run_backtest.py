"""
1. What this file does:
   Command-line interface (CLI) runner executing deterministic single-leg backtests (Task M4-08).
   Supports configuration loading, parameter overrides, schema validation, artifact generation,
   and execution on both synthetic benchmark data and real historical DuckDB lake options data.

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §19.1, §19.2 and MASTER §4:
     - CLI flags: --config, --validate, --override, --output-dir, --lake, --lake-path, --symbol, --limit.
     - Parses and validates 39-field EngineRunConfig.
     - Supports two execution data modes:
         * Synthetic Benchmark Mode (default): Generates deterministic intrabar 1-min / 5-min sessions.
         * Real Market Lake Mode (--lake): Reads real historical option candles from DuckDB lake.
     - Instantiates BacktestRunner and outputs summary metrics to stdout.
     - Emits 5 mandatory provenance artifacts: run_config.json, manifest.json, ledger.parquet, metrics.json, code_fingerprint.json.
     - Guarantees fail-closed exit codes: 0 on success, non-zero on validation/runtime errors.

3. Elements in the file:
   - parse_override_args: Parses key=value CLI override pairs into typed values.
   - load_lake_bars: Queries and formats real historical option candles from DuckDB lake.
   - main: CLI entry point coordinating argument parsing, validation, data loading, and execution.

4. Final output of the file:
   - CLI executable script emitting structured stdout and writing runs/{run_id}/ artifacts.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from packages.domain import Paise
from packages.engine.config import EngineRunConfig
from packages.engine.runner import BacktestRunner


def parse_override_args(override_list: List[str]) -> Dict[str, Any]:
    """
    1. The use of function:
       Parses a list of key=value strings into a typed Python dictionary.

    2. How does the specific function work:
       Splits each string on the first '=' and attempts JSON/int/float conversion before string fallback.

    3. Concepts used in the function:
       Dynamic CLI argument override parsing.

    4. Places where this function is imported and used:
       Called in main() of tools/run_backtest.py.

    5. Final output of the function, before and after:
       Before: Raw strings like ["lots=2", "capital_paise=15000000"].
       After: Typed dictionary {"lots": 2, "capital_paise": 15000000}.
    """
    overrides: Dict[str, Any] = {}
    for item in override_list:
        if "=" not in item:
            continue
        key, val = item.split("=", 1)
        key = key.strip()
        val = val.strip()

        # Type coercion
        if val.lower() == "true":
            overrides[key] = True
        elif val.lower() == "false":
            overrides[key] = False
        elif val.isdigit():
            overrides[key] = int(val)
        else:
            try:
                overrides[key] = float(val)
            except ValueError:
                overrides[key] = val
    return overrides


def load_lake_bars(
    lake_path: str = "Data/lake/quantview.duckdb",
    symbol: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """
    1. The use of function:
       Loads real historical option candles from the DuckDB analytical data lake for backtesting.

    2. How does the specific function work:
       - Connects to DuckDB lake at lake_path in read-only mode.
       - Queries v_candles_options filtering on active candles with volume > 0.
       - Converts INR floating-point prices to exact integer Paise (p * 100).
       - Extracts timestamp, open/high/low/close paise, volume, flat-bar status, and symbol.

    3. Concepts used in the function:
       Analytical data lake extraction, integer paise quantization.

    4. Places where this function is imported and used:
       Called in main() when --lake flag is passed to tools/run_backtest.py.

    5. Final output of the function, before and after:
       Before: DuckDB analytical views. After: List of validated CandleBar dictionary dicts.
    """
    import duckdb

    if not os.path.exists(lake_path):
        raise FileNotFoundError(f"DuckDB lake database not found at: {lake_path}")

    con = duckdb.connect(lake_path, read_only=True)
    try:
        if symbol:
            query = """
                SELECT epoch(bar_start) as ts,
                       cast(open * 100 as bigint) as op,
                       cast(high * 100 as bigint) as hp,
                       cast(low * 100 as bigint) as lp,
                       cast(close * 100 as bigint) as cp,
                       volume,
                       strftime(bar_start, '%H:%M') as t_str,
                       symbol,
                       coalesce(is_flat_bar, false) as is_flat
                FROM v_candles_options
                WHERE symbol = ? AND volume > 0
                ORDER BY bar_start ASC
                LIMIT ?
            """
            rows = con.execute(query, [symbol, limit]).fetchall()
        else:
            query = """
                SELECT epoch(bar_start) as ts,
                       cast(open * 100 as bigint) as op,
                       cast(high * 100 as bigint) as hp,
                       cast(low * 100 as bigint) as lp,
                       cast(close * 100 as bigint) as cp,
                       volume,
                       strftime(bar_start, '%H:%M') as t_str,
                       symbol,
                       coalesce(is_flat_bar, false) as is_flat
                FROM v_candles_options
                WHERE volume > 0
                ORDER BY bar_start ASC
                LIMIT ?
            """
            rows = con.execute(query, [limit]).fetchall()
    finally:
        con.close()

    bars: List[Dict[str, Any]] = []
    for r in rows:
        bars.append({
            "timestamp": int(r[0]),
            "open_paise": int(r[1]),
            "high_paise": int(r[2]),
            "low_paise": int(r[3]),
            "close_paise": int(r[4]),
            "volume": int(r[5]),
            "time_str": r[6],
            "symbol": r[7],
            "is_flat_bar": bool(r[8]),
        })
    return bars


def main() -> int:
    """
    1. The use of function:
       Main execution entrypoint for backtest CLI runner.

    2. How does the specific function work:
       - Configures argparse with --config, --validate, --override, --output-dir, --lake, --lake-path, --symbol, --limit.
       - Loads config JSON from disk if provided.
       - Applies overrides and validates via EngineRunConfig.
       - If --validate passed, outputs 'CONFIG VALID' with config hash and exits 0.
       - If --lake passed, extracts real historical candles from DuckDB lake.
       - Otherwise builds synthetic benchmark bars.
       - Executes BacktestRunner, prints structured summary to stdout, and exits 0.

    3. Concepts used in the function:
       Command-line process interface, fail-closed configuration validation.

    4. Places where this function is imported and used:
       Executed from shell: python tools/run_backtest.py [options].

    5. Final output of the function, before and after:
       Before: Shell invocation. After: Integer exit code (0 on success, non-zero on failure).
    """
    parser = argparse.ArgumentParser(description="QuantView Deterministic Backtest Runner (Task M4-08)")
    parser.add_argument("--config", type=str, help="Path to EngineRunConfig JSON file", required=False)
    parser.add_argument("--validate", action="store_true", help="Validate configuration schema only and exit")
    parser.add_argument("--override", nargs="*", default=[], help="Override parameters as key=value pairs")
    parser.add_argument("--output-dir", type=str, default=None, help="Custom output directory for artifacts")
    parser.add_argument("--lake", action="store_true", help="Load real historical option bars from DuckDB lake")
    parser.add_argument("--lake-path", type=str, default="Data/lake/quantview.duckdb", help="Path to DuckDB lake")
    parser.add_argument("--symbol", type=str, default=None, help="Specific option symbol to load from lake")
    parser.add_argument("--limit", type=int, default=500, help="Maximum candle bars to load from lake")

    args = parser.parse_args()

    # Load configuration dictionary
    config_dict: Dict[str, Any] = {}
    if args.config:
        if not os.path.exists(args.config):
            sys.stderr.write(f"ERROR: Config file not found: {args.config}\n")
            return 1
        with open(args.config, "r", encoding="utf-8") as f:
            config_dict = json.load(f)
    else:
        # Default baseline configuration for interactive / manual CLI execution
        config_dict = {
            "run_id": "manual_cli_run",
            "start_date": "2025-01-02",
            "end_date": "2025-01-02",
            "strategy_id": "LongCETrendFollowing",
            "capital_paise": 10_000_000,
            "lots": 1,
        }

    # Apply overrides
    if args.override:
        overrides = parse_override_args(args.override)
        config_dict.update(overrides)

    # Validate EngineRunConfig schema
    try:
        run_config = EngineRunConfig(**config_dict)
    except Exception as e:
        sys.stderr.write(f"CONFIG VALIDATION FAILED: {e}\n")
        return 2

    if args.validate:
        sys.stdout.write(f"CONFIG VALID: hash={run_config.compute_config_hash()}\n")
        return 0

    # Load bars based on mode
    if args.lake:
        try:
            bars = load_lake_bars(
                lake_path=args.lake_path,
                symbol=args.symbol,
                limit=args.limit,
            )
            if not bars:
                sys.stderr.write(f"ERROR: No candle bars retrieved from lake at {args.lake_path}\n")
                return 3
        except Exception as e:
            sys.stderr.write(f"LAKE DATA EXTRACTION FAILED: {e}\n")
            return 3
    else:
        # Default synthetic benchmark bars (75 bars representing a 5-minute session)
        bars = []
        base_price = 15000  # Rs 150 in paise
        for i in range(75):
            p = base_price + (i * 20)
            hh = i // 12 + 9
            mm = (i % 12) * 5 + 15
            if mm >= 60:
                hh += 1
                mm -= 60
            bars.append({
                "timestamp": 1735703700 + (i * 300),
                "open_paise": p,
                "high_paise": p + 50,
                "low_paise": p - 30,
                "close_paise": p + 20,
                "volume": 500,
                "is_flat_bar": False,
                "time_str": f"{hh:02d}:{mm:02d}",
                "symbol": "NIFTY25JAN24000CE",
            })

    runner = BacktestRunner(config=run_config, output_dir=args.output_dir)
    result = runner.run(bars=bars)

    sys.stdout.write(f"BACKTEST SUCCESS: run_id={result.run_id}\n")
    sys.stdout.write(f"Total Trades: {result.total_trades}\n")
    sys.stdout.write(f"Gross Realized P&L: Rs {result.metrics.gross_realized_pnl_paise / 100:.2f}\n")
    sys.stdout.write(f"Total Fees: Rs {result.metrics.total_fees_paise / 100:.2f}\n")
    sys.stdout.write(f"Net Realized P&L: Rs {result.metrics.net_realized_pnl_paise / 100:.2f}\n")
    sys.stdout.write(f"Final Equity: Rs {result.final_equity_paise / 100:.2f}\n")
    sys.stdout.write(f"Artifacts written to: {result.output_dir}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
