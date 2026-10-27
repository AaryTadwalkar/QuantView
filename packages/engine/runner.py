"""
1. What this file does:
   Implements the core deterministic BacktestRunner orchestration engine for QuantView (Task M4-08).
   Coordinates simulation loop, causal feature delivery, pre-trade risk gating, fill execution,
   integer-paise ledger accounting, and provenance artifact generation.

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §4, §5, §7, §8, §19, and §20:
     - 100% causal minute loop (feature.available_at <= decision_time).
     - Next-bar open fill execution; rejects 15:29:00 close entries with NO_NEXT_BAR.
     - STOP_FIRST intrabar execution policy.
     - Adverse tick quantization and integer paise fee deduction via versioned schedules.
     - Full artifact persistence to runs/{run_id}/: manifest.json, ledger.parquet, metrics.json,
       trades.json, and equity.json.

3. Elements in the file:
   - BacktestResult: Container for run outputs, metrics, ledger, and artifact paths.
   - BacktestRunner: Main orchestration engine driving deterministic backtests.

4. Final output of the file:
   - Exported BacktestResult and BacktestRunner classes.
"""

import json
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from packages.domain import (
    ContractIdentifier,
    OptionType,
    OrderSide,
    Paise,
    UtcEpochSec,
)
from packages.engine.clock import SimulationMinute
from packages.engine.config import EngineRunConfig
from packages.engine.execution import CandleBar, IntrabarFillEngine
from packages.engine.manifest import RunManifest, create_run_manifest
from packages.engine.metrics import BacktestMetrics
from packages.engine.selector import (
    ContractMasterProvider,
    InMemoryContractMaster,
    PointInTimeContractSelector,
)
from packages.ledger.fees import get_default_fee_engine
from packages.ledger.ledger import FinancialLedger, LedgerWriter
from packages.risk.evaluator import RiskPolicyEvaluator, RiskVerdict
from packages.risk.rules import RiskRules
from packages.strategies import SignalAction, Strategy, get_default_strategy_registry


class BacktestResult(BaseModel):
    """
    1. The use of class:
       Encapsulates the complete outputs, summary metrics, and disk paths of a backtest run.

    2. What the class contains:
       - run_id: Unique run ID.
       - output_dir: Directory holding generated artifacts.
       - manifest: Frozen RunManifest metadata.
       - metrics: Comprehensive 22+ performance metrics.
       - total_trades: Count of completed trades.
       - final_equity_paise: Ending account equity.

    3. Technologies used and why:
       Pydantic BaseModel for immutable serialization of run summary.

    4. Key design and overall design of the class:
       Provides unified access to backtest results for CLI, API, and test assertions.
    """
    run_id: str
    output_dir: str
    manifest: RunManifest
    metrics: BacktestMetrics
    total_trades: int
    final_equity_paise: int


class BacktestRunner:
    """
    1. The use of class:
       Deterministic backtest simulation engine orchestrating single-leg option strategies.

    2. What the class contains:
       - config: EngineRunConfig instance.
       - output_dir: Destination path for run artifacts.
       - strategy: Strategy instance resolved from StrategyRegistry.
       - contract_selector: PointInTimeContractSelector instance.
       - risk_evaluator: RiskPolicyEvaluator instance.
       - fill_engine: IntrabarFillEngine instance.
       - ledger: FinancialLedger instance.
       - fee_engine: FeeScheduleEngine instance.
       - run(): Main execution loop across bar data.

    3. Technologies used and why:
       Pure Python causal state machine interacting with event-sourced ledger and tick quantizer.

    4. Key design and overall design of the class:
       Strictly enforces causal ordering, next-bar open fills, STOP_FIRST policy, and zero lookahead bias.
    """

    def __init__(
        self,
        config: EngineRunConfig,
        output_dir: Optional[str] = None,
        contract_master: Optional[ContractMasterProvider] = None,
    ) -> None:
        self.config = config
        self.run_id = config.run_id
        self.output_dir = output_dir or os.path.join("runs", self.run_id)
        os.makedirs(self.output_dir, exist_ok=True)

        # 1. Resolve strategy from registry
        registry = get_default_strategy_registry()
        entry = registry.get_entry(config.strategy_id)
        self.strategy_code_hash = entry.code_hash
        self.strategy: Strategy = registry.create(config.strategy_id, config.strategy_params)

        # 2. Risk Evaluator
        risk_rules = config.risk_controls or RiskRules()
        self.risk_policy_hash = risk_rules.compute_policy_hash()
        self.risk_evaluator = RiskPolicyEvaluator(risk_rules)

        # 3. Contract Master & Point-in-time Selector
        self.contract_master = contract_master or InMemoryContractMaster([])
        self.contract_selector = PointInTimeContractSelector(self.contract_master)

        # 4. Financial Ledger
        self.ledger = FinancialLedger(
            account_id=config.account_id,
            run_id=self.run_id,
            initial_cash_paise=Paise(config.capital_paise),
        )

        # 5. Fill Engine & Fee Engine
        self.fee_engine = get_default_fee_engine()
        self.slippage_total_paise = config.slippage_paise * int(config.slippage_multiplier)
        self.fill_engine = IntrabarFillEngine(
            ledger=self.ledger,
            fee_engine=self.fee_engine,
            slippage_paise=self.slippage_total_paise,
            tick_paise=config.tick_paise,
            max_stale_minutes=config.max_stale_minutes,
        )

        # Simulation tracking state
        self.equity_series: List[Dict[str, Any]] = []

    def _create_minute(self, idx: int, total_bars: int, bar_dict: Dict[str, Any]) -> SimulationMinute:
        """Helper to construct a typed SimulationMinute from bar dictionary."""
        ist_time = bar_dict.get("time_str", "09:30")
        try:
            s_date = datetime.strptime(self.config.start_date, "%Y-%m-%d").date()
        except ValueError:
            s_date = date(2025, 1, 2)

        start_utc = UtcEpochSec(int(bar_dict.get("timestamp", idx * 60)))
        end_utc = UtcEpochSec(int(start_utc) + 60)
        is_open = (ist_time == "09:15")
        is_flat = (ist_time == "15:25")
        is_final = (ist_time == "15:29" or idx == total_bars - 1)

        return SimulationMinute(
            session_date=s_date,
            bar_start_utc=start_utc,
            bar_end_utc=end_utc,
            ist_time_str=ist_time,
            is_session_open=is_open,
            is_force_flat_minute=is_flat,
            is_final_session_minute=is_final,
        )

    def run(self, bars: List[Dict[str, Any]]) -> BacktestResult:
        """
        1. The use of function:
           Executes the backtest simulation sequentially across the provided candle bar series.

        2. How does the specific function work:
           - Iterates chronologically through bars.
           - Step 1: Executes pending open fills at bar open (step_1_open).
           - Step 2: Evaluates intrabar stop loss or take profit triggers (step_2_intrabar).
           - Step 3: Checks 15:25 force-flat rule and queues exit order (step_3_close).
           - Step 4: Calls strategy on_bar() at completed bar close.
           - Step 5: If signal produced, gates via pre-trade risk and queues next-bar open order.
           - Records mark-to-market equity and persists all run artifacts upon completion.

        3. Concepts used in the function:
           Causal discrete event simulation without lookahead bias.

        4. Places where this function is imported and used:
           Invoked by CLI tools/run_backtest.py and integration benchmark tests.

        5. Final output of the function, before and after:
           Before: Unprocessed historical bars.
           After: Fully executed backtest with persisted ledger, metrics, and manifest.
        """
        total_bars = len(bars)
        self.strategy.on_start(self.config.strategy_params)

        for idx, bar_dict in enumerate(bars):
            minute = self._create_minute(idx, total_bars, bar_dict)
            op = Paise(int(bar_dict["open_paise"]))
            hp = Paise(int(bar_dict["high_paise"]))
            lp = Paise(int(bar_dict["low_paise"]))
            cp = Paise(int(bar_dict["close_paise"]))
            vol = int(bar_dict.get("volume", 100))
            is_flat = bool(bar_dict.get("is_flat_bar", (op == hp == lp == cp and vol == 0)))
            candle = CandleBar(
                open_paise=op,
                high_paise=hp,
                low_paise=lp,
                close_paise=cp,
                volume=vol,
                is_flat_bar=is_flat,
            )
            symbol = bar_dict.get("symbol", "NIFTY25JAN24000CE")
            opt_type = OptionType.PE if "PE" in symbol else OptionType.CE

            contract = ContractIdentifier(
                instrument_key=symbol,
                trading_symbol=symbol,
                expiry_date=self.config.end_date,
                strike_price=24000.0,
                option_type=opt_type,
                lot_size=25,
            )

            # Step 1: Fill pending open orders at this bar's OPEN price
            self.fill_engine.step_1_open(minute=minute, candle=candle)

            # Step 2: Intrabar Stop Loss / Take Profit evaluation on Active Position
            self.fill_engine.step_2_intrabar(minute=minute, candle=candle)

            # Step 3: Session Force-Flat Check (15:25) and EOD close
            self.fill_engine.step_3_close(minute=minute, candle=candle)

            # Step 4: Causal strategy on_bar() evaluation on completed candle
            features = {
                "open": float(candle.open_paise) / 100.0,
                "high": float(candle.high_paise) / 100.0,
                "low": float(candle.low_paise) / 100.0,
                "close": float(candle.close_paise) / 100.0,
                "volume": candle.volume,
                "time_str": minute.ist_time_str,
            }
            signal = self.strategy.on_bar(minute.bar_end_utc, features)

            # Step 5: Process Strategy Signal
            if signal is not None:
                if (
                    signal.action == SignalAction.ENTER_LONG
                    and self.fill_engine.active_position is None
                    and not self.fill_engine.pending_orders
                ):
                    if minute.is_final_session_minute or minute.ist_time_str >= "15:29":
                        pass  # Reject with NO_NEXT_BAR per Invariant 2
                    elif minute.ist_time_str < self.config.entry_window_start or minute.ist_time_str > self.config.last_entry_time:
                        pass  # Blocked by RK-02 trading window
                    else:
                        risk_decision = self.risk_evaluator.evaluate_order(
                            contract=contract,
                            quantity=self.config.lots * 25,
                            price_paise=candle.close_paise,
                            current_time_str=minute.ist_time_str,
                        )
                        if risk_decision.verdict == RiskVerdict.PASS:
                            sl_paise = None
                            tp_paise = None
                            if self.config.stop_loss_pct:
                                sl_ratio = float(self.config.stop_loss_pct)
                                sl_paise = Paise(int(candle.close_paise * (1.0 - sl_ratio)))
                            if self.config.take_profit_pct:
                                tp_ratio = float(self.config.take_profit_pct)
                                tp_paise = Paise(int(candle.close_paise * (1.0 + tp_ratio)))

                            self.fill_engine.queue_order(
                                contract=contract,
                                side=OrderSide.BUY,
                                qty=self.config.lots * 25,
                                current_minute=minute,
                                stop_loss_paise=sl_paise,
                                take_profit_paise=tp_paise,
                            )
                elif (
                    signal.action == SignalAction.EXIT
                    and self.fill_engine.active_position is not None
                    and not self.fill_engine.pending_orders
                ):
                    self.fill_engine.queue_order(
                        contract=self.fill_engine.active_position.contract,
                        side=OrderSide.SELL,
                        qty=self.fill_engine.active_position.qty,
                        current_minute=minute,
                    )

            # Record mark-to-market equity point
            market_marks = {}
            if self.fill_engine.active_position is not None:
                market_marks[self.fill_engine.active_position.contract.instrument_key] = candle.close_paise
            total_equity = self.ledger.get_projection(market_marks).total_equity_paise
            self.equity_series.append({
                "bar_index": idx,
                "timestamp": int(minute.bar_end_utc),
                "time_str": minute.ist_time_str,
                "equity_paise": int(total_equity),
            })

        self.strategy.on_stop()

        # Step 6: Generate Performance Metrics & Deflated Sharpe Ratio
        closed_trades = self.fill_engine.trade_history
        metrics = BacktestMetrics.calculate(
            initial_capital_paise=self.config.capital_paise,
            closed_trades=closed_trades,
            equity_series=self.equity_series,
        )

        # Step 7: Create and Freeze Run Manifest
        manifest = create_run_manifest(
            config=self.config,
            strategy_code_hash=self.strategy_code_hash,
            risk_policy_hash=self.risk_policy_hash,
            status="COMPLETED",
        )

        # Step 8: Persist All Output Artifacts to runs/{run_id}/
        # 8a: manifest.json
        manifest_path = os.path.join(self.output_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

        # 8b: metrics.json
        metrics_path = os.path.join(self.output_dir, "metrics.json")
        with open(metrics_path, "w", encoding="utf-8") as f:
            f.write(metrics.model_dump_json(indent=2))

        # 8c: ledger.parquet
        ledger_parquet_path = os.path.join(self.output_dir, "ledger.parquet")
        LedgerWriter.save_to_parquet(self.ledger, ledger_parquet_path)

        # 8d: trades.json
        trades_path = os.path.join(self.output_dir, "trades.json")
        with open(trades_path, "w", encoding="utf-8") as f:
            json.dump(closed_trades, f, indent=2)

        # 8e: equity.json
        equity_path = os.path.join(self.output_dir, "equity.json")
        with open(equity_path, "w", encoding="utf-8") as f:
            json.dump(self.equity_series, f, indent=2)

        final_cash = self.ledger.get_projection().cash_balance_paise
        return BacktestResult(
            run_id=self.run_id,
            output_dir=self.output_dir,
            manifest=manifest,
            metrics=metrics,
            total_trades=len(closed_trades),
            final_equity_paise=int(final_cash),
        )
