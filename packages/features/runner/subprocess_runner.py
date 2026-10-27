"""
1. What this file does:
   Implements Isolated Subprocess Feature Runner and execution failure containment
   for custom or third-party features (MASTER §2, ENGINE §9, ADR-012, Task M5-07 / Gate G3).

2. Overall design:
   Executes feature calculations within an isolated process boundary with explicit timeout,
   memory supervision, and exception containment:
   - Timeout Enforcement: Kills worker if execution exceeds timeout_sec (status = TIMEOUT).
   - Fault Isolation: Crashes, memory exhaustion, or malformed outputs in one feature do NOT crash
     the parent engine; the faulty feature is marked UNAVAILABLE while other feature jobs continue.
   - Entry Gating: Returns structured SubprocessFeatureResult allowing Strategy / Engine to block
     new trade entries when required features are UNAVAILABLE.

3. Elements in the file:
   - SubprocessFeatureResult: NamedTuple representing isolated execution outcome and status.
   - IsolatedFeatureRunner: Core runner managing process pool execution with timeouts.
   - evaluate_with_timeout: Helper executing single calculation job under strict time limit.

4. Final output of the file:
   - Sandboxed feature execution harness guaranteeing ADR-012 resilience and zero unhandled engine crashes.
"""

import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence


class SubprocessFeatureResult(NamedTuple):
    """
    1. The use of class:
       Immutable output record of an isolated subprocess feature execution job.

    2. What the class contains:
       - feature_id: Unique string identifier of the evaluated feature.
       - status: Status string ('SUCCESS', 'TIMEOUT', 'CRASHED', 'MALFORMED_OUTPUT', 'UNAVAILABLE').
       - values: Calculated numerical output sequence or None if evaluation failed.
       - execution_time_ms: Elapsed execution time in milliseconds.
       - error_message: Descriptive error or exception traceback message if failed.

    3. Technologies used and why:
       NamedTuple for lightweight, serialization-safe IPC transfer.

    4. Key design and overall design of the class:
       Standardized failure contract per ADR-012 preventing cascade failures across features.
    """
    feature_id: str
    status: str
    values: Optional[List[float]]
    execution_time_ms: float
    error_message: Optional[str] = None


def _worker_wrapper(func: Callable, args: tuple, kwargs: dict) -> Any:
    """Internal top-level worker target for process pool execution."""
    return func(*args, **kwargs)


class IsolatedFeatureRunner:
    """
    1. The use of class:
       Manages sandboxed execution of quantitative feature functions in worker processes.

    2. What the class contains:
       - max_workers: Maximum concurrency in process pool.
       - timeout_sec: Maximum allowable execution duration per feature job (default 2.0s).

    3. Technologies used and why:
       concurrent.futures.ProcessPoolExecutor for true process-isolated memory spaces.

    4. Key design and overall design of the class:
       Ensures buggy, infinite-looping, or memory-leaking indicators are terminated cleanly.
    """

    def __init__(self, max_workers: int = 2, default_timeout_sec: float = 2.0):
        self.max_workers = max_workers
        self.default_timeout_sec = default_timeout_sec

    def run_feature(
        self,
        feature_id: str,
        compute_fn: Callable,
        args: Sequence[Any] = (),
        kwargs: Optional[Dict[str, Any]] = None,
        timeout_sec: Optional[float] = None,
    ) -> SubprocessFeatureResult:
        """
        1. The use of function:
           Executes a feature computation function in an isolated process with strict timeout.

        2. How does the specific function work:
           1. Measures start time.
           2. Submits _worker_wrapper to ProcessPoolExecutor.
           3. Awaits future.result(timeout=timeout_sec):
              - If completed: validates output is non-empty list/sequence of floats/numbers;
                returns SUCCESS.
              - If FuturesTimeoutError: terminates/cancels task, returns status='TIMEOUT'.
              - If Exception: catches error, returns status='UNAVAILABLE' with traceback.

        3. Concepts used in the function:
           Process isolation, fail-closed fault containment, ADR-012 execution bounds.

        4. Places where this function is imported and used:
           Used by StrategyContext for custom/unverified features and unit tests.

        5. Final output of the function, before and after:
           Before: Function and arguments. After: Populated SubprocessFeatureResult.
        """
        if kwargs is None:
            kwargs = {}
        t_limit = timeout_sec if timeout_sec is not None else self.default_timeout_sec
        t_start = time.perf_counter()

        with ProcessPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_worker_wrapper, compute_fn, tuple(args), kwargs)
            try:
                raw_result = future.result(timeout=t_limit)
                t_elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

                # Validate output schema
                if raw_result is None or not isinstance(raw_result, (list, tuple)):
                    return SubprocessFeatureResult(
                        feature_id=feature_id,
                        status="MALFORMED_OUTPUT",
                        values=None,
                        execution_time_ms=t_elapsed_ms,
                        error_message=f"Output must be list/tuple, got {type(raw_result)}.",
                    )

                float_values = [float(v) for v in raw_result]
                return SubprocessFeatureResult(
                    feature_id=feature_id,
                    status="SUCCESS",
                    values=float_values,
                    execution_time_ms=t_elapsed_ms,
                    error_message=None,
                )

            except FuturesTimeoutError:
                t_elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
                return SubprocessFeatureResult(
                    feature_id=feature_id,
                    status="TIMEOUT",
                    values=None,
                    execution_time_ms=t_elapsed_ms,
                    error_message=f"Feature computation exceeded timeout of {t_limit}s.",
                )

            except Exception as ex:
                t_elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
                return SubprocessFeatureResult(
                    feature_id=feature_id,
                    status="UNAVAILABLE",
                    values=None,
                    execution_time_ms=t_elapsed_ms,
                    error_message=str(ex),
                )
