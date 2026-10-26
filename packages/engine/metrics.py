"""
1. What this file does:
   Computes performance metrics, risk-adjusted returns, drawdown profiles, time-of-day breakdowns,
   and the Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR) for QuantView backtests (Task M4-15).

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §20.1, §20.2, §20.2.1, and §20.3:
     - Calculates 22+ deterministic metrics from closed trades and equity series in exact integer paise.
     - Implements authoritative Deflated Sharpe Ratio with strict frequency consistency (daily returns).
     - Strictly enforces trial-accounting validity gate: if N < 2 or trial dispersion is undefined/zero,
       emits null with reason 'INSUFFICIENT_TRIAL_HISTORY (N < 2)'.
     - Recomputable from frozen ledger/equity artifacts with zero lookahead bias.

3. Elements in the file:
   - standard_normal_cdf: Pure Python standard normal cumulative distribution function.
   - standard_normal_ppf: Pure Python inverse normal CDF (probit) using rational approximation.
   - DeflatedSharpeResult: Typed container for DSR calculation and audit metadata.
   - compute_deflated_sharpe_ratio: Authoritative Bailey & López de Prado (2014) DSR engine.
   - BacktestMetrics: Comprehensive 22+ performance metrics calculation engine.

4. Final output of the file:
   - Exported metric calculators and BacktestMetrics model.
"""

import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from packages.domain import Paise


def standard_normal_cdf(x: float) -> float:
    """
    1. The use of function:
       Computes standard normal cumulative distribution function Phi(x).

    2. How does the specific function work:
       Uses standard math.erf: Phi(x) = 0.5 * (1.0 + math.erf(x / sqrt(2))).

    3. Concepts used in the function:
       Gaussian error function approximation.

    4. Places where this function is imported and used:
       Used by compute_deflated_sharpe_ratio.

    5. Final output of the function, before and after:
       Before: Real number x. After: Cumulative probability in [0, 1].
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def standard_normal_ppf(p: float) -> float:
    """
    1. The use of function:
       Computes the inverse standard normal cumulative distribution function (probit) Phi^-1(p).

    2. How does the specific function work:
       Uses Peter J. Acklam's rational approximation algorithm yielding relative error < 1.15e-9.

    3. Concepts used in the function:
       Inverse Gaussian probit rational minimax approximation.

    4. Places where this function is imported and used:
       Used by compute_deflated_sharpe_ratio for expected maximum Sharpe ratio under the null.

    5. Final output of the function, before and after:
       Before: Probability p in (0, 1). After: Quantile z on the standard normal curve.
    """
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"Probability p must be strictly in (0, 1), got {p}")

    # Coefficients in rational approximations
    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)

    p_low = 0.02425
    p_high = 1.0 - p_low

    if p < p_low:
        # Rational approximation for lower region
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
               ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)
    elif p <= p_high:
        # Rational approximation for central region
        q = p - 0.5
        r = q * q
        return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5])*q / \
               (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1.0)
    else:
        # Rational approximation for upper region
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)


class DeflatedSharpeResult(BaseModel):
    """
    1. The use of class:
       Encapsulates the Deflated Sharpe Ratio result and audit metadata.

    2. What the class contains:
       - dsr: Optional float in [0, 1].
       - null_reason: Structured diagnostic reason when DSR is undefined.
       - T: Sample size (number of observations).
       - skewness, kurtosis: Sample third and fourth standardized moments.
       - N: Trial count from research_trials.
       - sigma_trials: Cross-trial Sharpe dispersion.
       - sr_expected_max: Expected maximum Sharpe under null hypothesis.
       - var_sr: Sampling variance of the observed Sharpe ratio.

    3. Technologies used and why:
       Pydantic v2 BaseModel for typed metrics serialization.

    4. Key design and overall design of the class:
       Complies strictly with ENGINE §20.2.1 audit metadata specification.
    """
    dsr: Optional[float] = None
    null_reason: Optional[str] = None
    T: int = 0
    skewness: float = 0.0
    kurtosis: float = 3.0
    N: int = 0
    sigma_trials: float = 0.0
    sr_daily: float = 0.0
    sr_expected_max: float = 0.0
    var_sr: float = 0.0


def compute_deflated_sharpe_ratio(
    daily_returns: List[float],
    trial_sharpes: Optional[List[float]] = None,
    n_trials: Optional[int] = None,
    sigma_trials: Optional[float] = None,
    risk_free_rate_daily: float = 0.0,
) -> DeflatedSharpeResult:
    """
    1. The use of function:
       Computes authoritative Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR).

    2. How does the specific function work:
       - Evaluates trial validity gate: requires N >= 2 and sigma_trials > 0.
       - Computes daily mean return, standard deviation, sample skewness (s), and non-excess kurtosis (k).
       - Computes daily observed Sharpe ratio: sr = mean(r - rf) / std(r).
       - Computes sampling variance: Var(sr) = (1 - s*sr + ((k - 1)/4)*sr^2) / (T - 1).
       - Computes expected maximum Sharpe ratio under the null hypothesis of multiple trials:
         sr_star = sigma_trials * ((1 - gamma)*Phi^-1(1 - 1/N) + gamma*Phi^-1(1 - 1/(N*e))).
       - Computes deflated statistic: DSR = Phi((sr - sr_star) / sqrt(Var(sr))).

    3. Concepts used in the function:
       Multiple testing correction, selection bias deflection, non-normality adjustments.

    4. Places where this function is imported and used:
       Imported by BacktestMetrics and verified by test_backtest_metrics_dsr.py.

    5. Final output of the function, before and after:
       Before: List of daily returns and trial distribution parameters.
       After: DeflatedSharpeResult containing exact DSR or structured null reason.
    """
    T = len(daily_returns)
    if T < 3:
        return DeflatedSharpeResult(
            null_reason=f"INSUFFICIENT_SAMPLE_SIZE (T={T} < 3)",
            T=T,
        )

    # Resolve N and cross-trial dispersion
    if trial_sharpes is not None and len(trial_sharpes) >= 2:
        n_trials = len(trial_sharpes)
        mean_trial = sum(trial_sharpes) / n_trials
        var_trial = sum((x - mean_trial) ** 2 for x in trial_sharpes) / (n_trials - 1)
        sigma_trials = math.sqrt(var_trial)
        if sigma_trials <= 1e-12:
            return DeflatedSharpeResult(
                null_reason="INSUFFICIENT_TRIAL_HISTORY (undefined or zero dispersion)",
                T=T,
                N=n_trials,
                sigma_trials=0.0,
            )
    elif n_trials is not None and n_trials >= 2 and sigma_trials is not None and sigma_trials > 0.0:
        pass
    else:
        return DeflatedSharpeResult(
            null_reason="INSUFFICIENT_TRIAL_HISTORY (N < 2)",
            T=T,
            N=n_trials or (len(trial_sharpes) if trial_sharpes else 1),
        )

    # Moments of daily return series
    mean_r = sum(daily_returns) / T
    excess_returns = [r - risk_free_rate_daily for r in daily_returns]
    mean_excess = sum(excess_returns) / T

    var_r = sum((r - mean_r) ** 2 for r in daily_returns) / (T - 1)
    if var_r <= 1e-12:
        return DeflatedSharpeResult(
            null_reason="ZERO_RETURN_VARIANCE",
            T=T,
            N=n_trials,
            sigma_trials=sigma_trials,
        )
    std_r = math.sqrt(var_r)

    # Sample skewness (s) and non-excess kurtosis (k)
    s = (sum((r - mean_r) ** 3 for r in daily_returns) / T) / (std_r ** 3)
    k = (sum((r - mean_r) ** 4 for r in daily_returns) / T) / (std_r ** 4)

    # Daily observed Sharpe ratio
    sr_daily = mean_excess / std_r

    # Sampling variance of daily Sharpe ratio
    var_sr_numerator = 1.0 - (s * sr_daily) + (((k - 1.0) / 4.0) * (sr_daily ** 2))
    if var_sr_numerator <= 0.0 or T <= 1:
        return DeflatedSharpeResult(
            null_reason="INVALID_SHARPE_VARIANCE",
            T=T,
            skewness=s,
            kurtosis=k,
            N=n_trials,
            sigma_trials=sigma_trials,
            sr_daily=sr_daily,
        )
    var_sr = var_sr_numerator / (T - 1)
    std_sr = math.sqrt(var_sr)

    # Expected maximum Sharpe ratio under the null: Bailey & López de Prado (2014)
    # Euler-Mascheroni constant
    gamma = 0.57721566490153286
    p1 = 1.0 - (1.0 / n_trials)
    p2 = 1.0 - (1.0 / (n_trials * math.e))

    z1 = standard_normal_ppf(p1)
    z2 = standard_normal_ppf(p2)
    sr_expected_max = sigma_trials * (((1.0 - gamma) * z1) + (gamma * z2))

    # Deflated Sharpe Ratio statistic
    z_dsr = (sr_daily - sr_expected_max) / std_sr
    dsr = standard_normal_cdf(z_dsr)

    return DeflatedSharpeResult(
        dsr=float(dsr),
        null_reason=None,
        T=T,
        skewness=float(s),
        kurtosis=float(k),
        N=n_trials,
        sigma_trials=float(sigma_trials),
        sr_daily=float(sr_daily),
        sr_expected_max=float(sr_expected_max),
        var_sr=float(var_sr),
    )


class BacktestMetrics(BaseModel):
    """
    1. The use of class:
       Computes and structures all 22+ canonical backtest performance metrics.

    2. What the class contains:
       Financial returns, win/loss stats, drawdown analysis, Sharpe/Sortino/Calmar,
       time-of-day split, and Deflated Sharpe Ratio.

    3. Technologies used and why:
       Pydantic BaseModel for immutable JSON serialization.

    4. Key design and overall design of the class:
       Strictly deterministic calculation derived from financial ledger and equity series.
    """
    initial_capital_paise: int
    final_equity_paise: int
    total_pnl_paise: int
    total_return_pct: float
    annualized_return_pct: float
    gross_realized_pnl_paise: int
    total_fees_paise: int
    net_realized_pnl_paise: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: Optional[float] = None
    expectancy_paise: float = 0.0
    max_drawdown_paise: int = 0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0
    max_consecutive_losses: int = 0
    daily_sharpe: Optional[float] = None
    annualized_sharpe: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    annualized_volatility_pct: Optional[float] = None
    time_of_day_pnl_paise: Dict[str, int] = Field(default_factory=dict)
    deflated_sharpe: Optional[DeflatedSharpeResult] = None

    @classmethod
    def calculate(
        cls,
        initial_capital_paise: int,
        closed_trades: List[Dict[str, Any]],
        equity_series: List[Dict[str, Any]],
        trial_sharpes: Optional[List[float]] = None,
        risk_free_rate_annual: float = 0.0,
    ) -> "BacktestMetrics":
        """
        1. The use of function:
           Factory method calculating 22+ metrics from closed trade records and equity snapshots.

        2. How does the specific function work:
           - Aggregates gross realized P&L, fees, and net realized P&L across trades.
           - Calculates winning/losing trade counts, win rate, profit factor, and expectancy.
           - Computes maximum peak-to-trough drawdown in paise and percentage, and drawdown duration.
           - Extracts daily returns from session-end equity snapshots and computes daily/annualized Sharpe,
             Sortino, Calmar, and volatility.
           - Bins trades into Asian/Kolkata session time-of-day buckets.
           - Computes Bailey & López de Prado (2014) DSR with trial validity check.

        3. Concepts used in the function:
           Financial quantitative accounting and statistical evaluation.

        4. Places where this function is imported and used:
           Used by BacktestRunner at backtest completion to emit runs/{run_id}/metrics.json.

        5. Final output of the function, before and after:
           Before: Raw lists of closed trades and equity snapshots.
           After: Comprehensive BacktestMetrics object.
        """
        total_trades = len(closed_trades)
        gross_pnl = sum(t.get("gross_pnl_paise", 0) for t in closed_trades)
        total_fees = sum(t.get("fee_paise", 0) for t in closed_trades)
        net_pnl = gross_pnl - total_fees

        final_equity = initial_capital_paise + net_pnl
        if equity_series:
            final_equity = equity_series[-1].get("equity_paise", final_equity)

        total_return_pct = ((final_equity - initial_capital_paise) / initial_capital_paise) * 100.0

        # Win/loss statistics
        wins = [t for t in closed_trades if t.get("net_pnl_paise", t.get("gross_pnl_paise", 0) - t.get("fee_paise", 0)) > 0]
        losses = [t for t in closed_trades if t.get("net_pnl_paise", t.get("gross_pnl_paise", 0) - t.get("fee_paise", 0)) < 0]
        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate_pct = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_wins = sum(t.get("gross_pnl_paise", 0) for t in wins)
        gross_losses = abs(sum(t.get("gross_pnl_paise", 0) for t in losses))
        profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else (999.0 if gross_wins > 0 else 0.0)
        expectancy_paise = (net_pnl / total_trades) if total_trades > 0 else 0.0

        # Max consecutive losses
        max_consec_losses = 0
        curr_losses = 0
        for t in closed_trades:
            pnl = t.get("net_pnl_paise", t.get("gross_pnl_paise", 0) - t.get("fee_paise", 0))
            if pnl < 0:
                curr_losses += 1
                if curr_losses > max_consec_losses:
                    max_consec_losses = curr_losses
            else:
                curr_losses = 0

        # Drawdown profile from equity series
        max_dd_paise = 0
        max_dd_pct = 0.0
        max_dd_duration = 0
        curr_dd_duration = 0
        peak_equity = initial_capital_paise

        for pt in equity_series:
            eq = pt.get("equity_paise", initial_capital_paise)
            if eq > peak_equity:
                peak_equity = eq
                curr_dd_duration = 0
            else:
                dd = peak_equity - eq
                if dd > max_dd_paise:
                    max_dd_paise = dd
                dd_pct = (dd / peak_equity) * 100.0 if peak_equity > 0 else 0.0
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct
                curr_dd_duration += 1
                if curr_dd_duration > max_dd_duration:
                    max_dd_duration = curr_dd_duration

        # Daily returns & annualized risk metrics
        daily_returns: List[float] = []
        if len(equity_series) >= 2:
            prev = equity_series[0].get("equity_paise", initial_capital_paise)
            for pt in equity_series[1:]:
                curr = pt.get("equity_paise", initial_capital_paise)
                if prev > 0:
                    daily_returns.append((curr - prev) / prev)
                prev = curr

        n_days = max(1, len(daily_returns))
        ann_return_pct = total_return_pct * (252.0 / n_days) if n_days > 0 else 0.0

        daily_sharpe = None
        ann_sharpe = None
        sortino = None
        ann_vol = None
        calmar = None

        if len(daily_returns) >= 2:
            mean_ret = sum(daily_returns) / len(daily_returns)
            var_ret = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            std_ret = math.sqrt(var_ret)
            ann_vol = std_ret * math.sqrt(252.0) * 100.0

            if std_ret > 1e-12:
                daily_rf = risk_free_rate_annual / 252.0
                daily_sharpe = (mean_ret - daily_rf) / std_ret
                ann_sharpe = daily_sharpe * math.sqrt(252.0)

            # Sortino
            downside_sq = [min(0.0, r) ** 2 for r in daily_returns]
            downside_dev = math.sqrt(sum(downside_sq) / len(downside_sq))
            if downside_dev > 1e-12:
                sortino = (mean_ret * math.sqrt(252.0)) / (downside_dev * math.sqrt(252.0))

            # Calmar
            if max_dd_pct > 0.0:
                calmar = ann_return_pct / max_dd_pct

        # Time of day P&L breakdown
        tod_pnl: Dict[str, int] = {
            "morning_09_15_11_30": 0,
            "midday_11_30_13_30": 0,
            "afternoon_13_30_15_30": 0,
        }
        for t in closed_trades:
            entry_time = t.get("entry_time", "")
            pnl = t.get("net_pnl_paise", t.get("gross_pnl_paise", 0) - t.get("fee_paise", 0))
            if "09:15" <= entry_time < "11:30":
                tod_pnl["morning_09_15_11_30"] += pnl
            elif "11:30" <= entry_time < "13:30":
                tod_pnl["midday_11_30_13_30"] += pnl
            else:
                tod_pnl["afternoon_13_30_15_30"] += pnl

        # Deflated Sharpe Ratio calculation
        dsr_result = compute_deflated_sharpe_ratio(
            daily_returns=daily_returns,
            trial_sharpes=trial_sharpes,
        )

        return cls(
            initial_capital_paise=initial_capital_paise,
            final_equity_paise=final_equity,
            total_pnl_paise=net_pnl,
            total_return_pct=round(total_return_pct, 4),
            annualized_return_pct=round(ann_return_pct, 4),
            gross_realized_pnl_paise=gross_pnl,
            total_fees_paise=total_fees,
            net_realized_pnl_paise=net_pnl,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_pct=round(win_rate_pct, 2),
            profit_factor=round(profit_factor, 4) if profit_factor is not None else None,
            expectancy_paise=round(expectancy_paise, 2),
            max_drawdown_paise=max_dd_paise,
            max_drawdown_pct=round(max_dd_pct, 4),
            max_drawdown_duration_bars=max_dd_duration,
            max_consecutive_losses=max_consec_losses,
            daily_sharpe=round(daily_sharpe, 4) if daily_sharpe is not None else None,
            annualized_sharpe=round(ann_sharpe, 4) if ann_sharpe is not None else None,
            sortino_ratio=round(sortino, 4) if sortino is not None else None,
            calmar_ratio=round(calmar, 4) if calmar is not None else None,
            annualized_volatility_pct=round(ann_vol, 4) if ann_vol is not None else None,
            time_of_day_pnl_paise=tod_pnl,
            deflated_sharpe=dsr_result,
        )
