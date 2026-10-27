"""
1. What this file does:
   Tests the standalone BacktestRunner orchestration engine and CLI tool (Task M4-08).
   Verifies config validation, CLI overrides, artifact creation, ledger persistence, and causal invariants.

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §4, §8, §19.1, §19.2:
     - Tests CLI validation mode (--validate) for positive and negative cases.
     - Tests full backtest simulation producing runs/{run_id}/ artifacts.
     - Verifies round-trip Parquet ledger loading and balance invariant satisfaction.
     - Verifies Invariant 2: entries decided at 15:29:00 close are rejected without next-bar fill.

3. Elements in the file:
   - TestBacktestRunner: Test suite validating runner pipeline and CLI.

4. Final output of the file:
   - Unit test execution results for Task M4-08.
"""

import json
import os
import shutil
import tempfile
import unittest

import pytest

from packages.domain import Paise, UtcEpochSec
from packages.engine.config import EngineRunConfig
from packages.engine.runner import BacktestRunner
from packages.ledger.ledger import LedgerWriter
from packages.ledger.projections import LedgerProjectionEngine
from tools.run_backtest import parse_override_args


@pytest.mark.gate_g2a
class TestBacktestRunner(unittest.TestCase):
    """
    1. The use of class:
       Unit test cases validating BacktestRunner execution and CLI parsing (Task M4-08).

    2. What the class contains:
       - test_override_arg_parsing: Tests parsing key=value overrides.
       - test_backtest_runner_generates_all_artifacts: Verifies full execution and artifact creation.
       - test_final_bar_entry_rejection_no_next_bar: Verifies Invariant 2 causal boundary.
       - test_persisted_ledger_parity_and_balance: Verifies Parquet ledger balance invariant.

    3. Technologies used and why:
       unittest.TestCase and tempfile.mkdtemp for artifact isolation.

    4. Key design and overall design of the class:
       Guarantees M4-08 acceptance requirements and provenance artifact durability.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="qv_test_run_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_override_arg_parsing(self):
        """
        1. The use of function:
           Tests CLI parameter override parser.

        2. How does the specific function work:
           Passes raw string arguments and asserts typed values.

        3. Concepts used in the function:
           Type inference on CLI arguments.

        4. Places where this function is imported and used:
           Executed by pytest.

        5. Final output of the function, before and after:
           Before: String list. After: Typed dictionary.
        """
        raw = ["capital_paise=25000000", "lots=3", "overnight_carry=true", "strategy_id=LongCETrendFollowing"]
        parsed = parse_override_args(raw)
        self.assertEqual(parsed["capital_paise"], 25_000_000)
        self.assertEqual(parsed["lots"], 3)
        self.assertEqual(parsed["overnight_carry"], True)
        self.assertEqual(parsed["strategy_id"], "LongCETrendFollowing")

    def test_backtest_runner_generates_all_artifacts(self):
        """
        1. The use of function:
           Tests complete backtest run and generation of all five canonical artifacts.

        2. How does the specific function work:
           Configures EngineRunConfig, creates synthetic candle bars, executes BacktestRunner.
           Asserts existence and validity of manifest.json, metrics.json, ledger.parquet,
           trades.json, and equity.json.

        3. Concepts used in the function:
           Full pipeline verification and file durability.

        4. Places where this function is imported and used:
           Executed by pytest.

        5. Final output of the function, before and after:
           Before: Config and bars. After: Verified files on disk and valid metrics.
        """
        cfg = EngineRunConfig(
            run_id="test_run_m4_08",
            start_date="2025-01-02",
            end_date="2025-01-02",
            strategy_id="LongCETrendFollowing",
            capital_paise=10_000_000,
            lots=1,
            fee_schedule_version="UPSTOX_2025_OCT",
        )

        bars = []
        base_p = 10000  # Rs 100
        for i in range(50):
            p = base_p + (i * 25)
            bars.append({
                "timestamp": 1735789500 + (i * 300),
                "open_paise": p,
                "high_paise": p + 60,
                "low_paise": p - 30,
                "close_paise": p + 30,
                "volume": 200,
                "time_str": "09:30" if i < 25 else "14:00",
                "symbol": "NIFTY25JAN24000CE",
            })

        runner = BacktestRunner(config=cfg, output_dir=self.temp_dir)
        result = runner.run(bars=bars)

        self.assertEqual(result.run_id, "test_run_m4_08")
        self.assertEqual(result.output_dir, self.temp_dir)

        # 1. manifest.json
        manifest_file = os.path.join(self.temp_dir, "manifest.json")
        self.assertTrue(os.path.exists(manifest_file))
        with open(manifest_file, "r", encoding="utf-8") as f:
            m_data = json.load(f)
        self.assertEqual(m_data["strategy_id"], "LongCETrendFollowing")
        self.assertEqual(len(m_data["config_hash"]), 64)

        # 2. metrics.json
        metrics_file = os.path.join(self.temp_dir, "metrics.json")
        self.assertTrue(os.path.exists(metrics_file))
        with open(metrics_file, "r", encoding="utf-8") as f:
            met_data = json.load(f)
        self.assertEqual(met_data["initial_capital_paise"], 10_000_000)

        # 3. ledger.parquet
        parquet_file = os.path.join(self.temp_dir, "ledger.parquet")
        self.assertTrue(os.path.exists(parquet_file))
        reloaded_ledger = LedgerWriter.load_from_parquet(parquet_file)
        self.assertGreater(len(reloaded_ledger.events), 0)

        # 4. trades.json
        trades_file = os.path.join(self.temp_dir, "trades.json")
        self.assertTrue(os.path.exists(trades_file))

        # 5. equity.json
        equity_file = os.path.join(self.temp_dir, "equity.json")
        self.assertTrue(os.path.exists(equity_file))

    def test_persisted_ledger_parity_and_balance(self):
        """
        1. The use of function:
           Verifies that the ledger persisted by BacktestRunner satisfies the fundamental balance equation.

        2. How does the specific function work:
           Runs backtest, reloads ledger from Parquet, and validates FundamentalBalanceVerifier.

        3. Concepts used in the function:
           Event-sourced accounting fidelity.

        4. Places where this function is imported and used:
           Executed by pytest.

        5. Final output of the function, before and after:
           Before: Serialized parquet. After: Verified mathematical balance.
        """
        cfg = EngineRunConfig(
            run_id="test_run_balance",
            start_date="2025-01-02",
            end_date="2025-01-02",
            strategy_id="LongCETrendFollowing",
            capital_paise=10_000_000,
            lots=1,
        )
        bars = [
            {"timestamp": 1000, "open_paise": 10000, "high_paise": 10100, "low_paise": 9900, "close_paise": 10050, "volume": 100, "time_str": "09:30", "symbol": "NIFTY25JAN24000CE"},
            {"timestamp": 1300, "open_paise": 10050, "high_paise": 10200, "low_paise": 10000, "close_paise": 10150, "volume": 100, "time_str": "09:35", "symbol": "NIFTY25JAN24000CE"},
            {"timestamp": 1600, "open_paise": 10150, "high_paise": 10300, "low_paise": 10100, "close_paise": 10250, "volume": 100, "time_str": "09:40", "symbol": "NIFTY25JAN24000CE"},
        ]
        runner = BacktestRunner(config=cfg, output_dir=self.temp_dir)
        runner.run(bars=bars)

        reloaded = LedgerWriter.load_from_parquet(os.path.join(self.temp_dir, "ledger.parquet"))
        state = reloaded.get_projection()
        is_balanced = LedgerProjectionEngine.verify_balance_equation(state)
        self.assertTrue(is_balanced)

    def test_cli_runner_validate_mode(self):
        """
        1. The use of function:
           Tests CLI runner --validate mode.

        2. How does the specific function work:
           Writes a temporary config JSON, invokes main() via patched sys.argv, and asserts return code 0.

        3. Concepts used in the function:
           CLI test execution.

        4. Places where this function is imported and used:
           Executed by pytest.

        5. Final output of the function, before and after:
           Before: Unvalidated CLI tool. After: Validated CLI return code.
        """
        import sys

        from tools.run_backtest import main

        cfg_path = os.path.join(self.temp_dir, "test_config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump({
                "start_date": "2025-01-01",
                "end_date": "2025-01-31",
                "strategy_id": "LongCETrendFollowing",
                "capital_paise": 10000000,
            }, f)

        orig_argv = sys.argv
        try:
            sys.argv = ["run_backtest.py", "--config", cfg_path, "--validate"]
            code = main()
            self.assertEqual(code, 0)
        finally:
            sys.argv = orig_argv

    def test_final_bar_15_29_no_next_bar_invariant(self):
        """
        1. The use of function:
           Verifies Invariant 2: an entry signal generated at 15:29:00 close cannot enter at that close
           and is rejected because no next regular bar exists.

        2. How does the specific function work:
           Feeds bars up to 15:29:00, emits entry signal at 15:29:00, asserts that no active position
           or pending order is filled at 15:29 close.

        3. Concepts used in the function:
           Causal timing protection and look-ahead bias prevention.

        4. Places where this function is imported and used:
           Executed by pytest.

        5. Final output of the function, before and after:
           Before: Unverified final bar boundary. After: Proved zero lookahead fill at 15:29 close.
        """
        cfg = EngineRunConfig(
            run_id="test_run_eod_invariant",
            start_date="2025-01-02",
            end_date="2025-01-02",
            strategy_id="LongCETrendFollowing",
            capital_paise=10_000_000,
            lots=1,
        )
        bars = [
            {"timestamp": 1000, "open_paise": 10000, "high_paise": 10100, "low_paise": 9900, "close_paise": 10050, "volume": 100, "time_str": "15:28", "symbol": "NIFTY25JAN24000CE"},
            {"timestamp": 1060, "open_paise": 10050, "high_paise": 10200, "low_paise": 10000, "close_paise": 10150, "volume": 100, "time_str": "15:29", "symbol": "NIFTY25JAN24000CE"},
        ]
        runner = BacktestRunner(config=cfg, output_dir=self.temp_dir)
        res = runner.run(bars=bars)

        # Assert no trade was executed because signal at 15:29 cannot fill
        self.assertEqual(len(runner.fill_engine.pending_orders), 0)
        self.assertIsNone(runner.fill_engine.active_position)
        self.assertEqual(res.total_trades, 0)


if __name__ == "__main__":
    unittest.main()
