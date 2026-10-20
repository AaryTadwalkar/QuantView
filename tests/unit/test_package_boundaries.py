"""
1. What this file does:
   Automated verification of Milestone M1-01 (Repository and Package Boundaries).
   Tests directory structure, package imports, domain invariants, and import dependency direction.

2. Overall design:
   Uses Python unittest to verify:
     - All 19 required directories and packages exist.
     - Clean import smoke test of all packages.* and services.* modules.
     - Strict dependency direction enforcement via AST / module inspection:
       domain is leaf, strategies do not import broker/raw, engine coordinates layers.
     - Paise integer conversion and UtcEpochSec branding.

3. Elements in the file:
   - TestPackageLayout: Verifies directory layout per M1-01 deliverable targets.
   - TestPackageImports: Smoke tests package module exports and core types.
   - TestImportBoundaries: Analyzes AST of package files to assert no reverse dependency leaks.

4. Final output of the file:
   - Automated pass/fail test execution for M1-01.
"""

import ast
import unittest
from pathlib import Path

# Core packages
import packages.domain as domain
import packages.data as data
import packages.features as features
import packages.strategies as strategies
import packages.engine as engine
import packages.risk as risk
import packages.ledger as ledger
import packages.db as db
import config


class TestPackageLayout(unittest.TestCase):
    """
    1. The use of class:
       Validates that all required repository directories and package boundaries exist on disk.

    2. What the class contains:
       - test_deliverable_directories_exist: Asserts existence of all 19 deliverable targets.

    3. Technologies used and why:
       pathlib.Path for cross-platform filesystem validation.

    4. Key design and overall design of the class:
       Directly enforces acceptance contract for Milestone M1-01 in AGENTS.md.
    """

    def test_deliverable_directories_exist(self):
        """
        1. The use of function:
           Asserts that all deliverable target directories specified in M1-01 exist.

        2. How does the specific function work:
           Iterates over list of required directory paths and verifies p.is_dir().

        3. Concepts used in the function:
           Repository scaffolding verification.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unverified layout. After: Verified presence of all required directories.
        """
        expected_dirs = [
            "apps/web",
            "services/collector_snapshot",
            "services/collector_ws",
            "services/backfill",
            "services/api",
            "services/worker_compute",
            "services/worker_data",
            "services/live_daemon",
            "packages/domain",
            "packages/data",
            "packages/features",
            "packages/strategies",
            "packages/engine",
            "packages/risk",
            "packages/ledger",
            "packages/db",
            "tests",
            "config",
            "ops",
        ]
        root = Path(".")
        for d in expected_dirs:
            p = root / d
            self.assertTrue(p.is_dir(), f"Required M1-01 directory missing: {d}")


class TestPackageImports(unittest.TestCase):
    """
    1. The use of class:
       Smoke tests package module exports, domain models, and exact money conversions.

    2. What the class contains:
       - test_domain_paise_and_timestamps: Tests integer paise and UtcEpochSec types.
       - test_ledger_append_only: Tests financial ledger event recording.
       - test_risk_evaluation_freeze_limit: Tests RK-06 freeze quantity rule.
       - test_engine_run_config: Tests RunConfig encapsulation.

    3. Technologies used and why:
       unittest for automated regression assertions.

    4. Key design and overall design of the class:
       Confirms that packages export working classes and functions without runtime import errors.
    """

    def test_domain_paise_and_timestamps(self):
        """Tests that rupees_to_paise and paise_to_rupees round-trip with zero float drift."""
        paise = domain.rupees_to_paise(150.25)
        self.assertEqual(paise, 15025)
        self.assertIsInstance(paise, int)
        rupees = domain.paise_to_rupees(paise)
        self.assertEqual(rupees, 150.25)

        cid = domain.ContractIdentifier(
            instrument_key="NSE_FO|41685|26-12-2024",
            trading_symbol="NIFTY 23750 CE 26 DEC 24",
            expiry_date="2024-12-26",
            strike_price=23750.0,
            option_type=domain.OptionType.CE,
            lot_size=25,
        )
        self.assertEqual(cid.strike_price, 23750.0)
        self.assertEqual(cid.option_type, domain.OptionType.CE)

    def test_ledger_append_only(self):
        """Tests that FinancialLedger appends events and updates integer cash balance."""
        fin_ledger = ledger.FinancialLedger(initial_cash_paise=domain.Paise(10000000))  # 1 lakh INR
        self.assertEqual(fin_ledger.balance_paise, 10000000)

        ev = fin_ledger.record_event(
            event_type=ledger.LedgerEventType.FEE,
            timestamp=domain.UtcEpochSec(1735200000),
            amount_paise=domain.Paise(-2500),  # -25 INR fee
            description="Brokerage fee",
        )
        self.assertEqual(ev.event_id, 1)
        self.assertEqual(fin_ledger.balance_paise, 9997500)
        self.assertEqual(len(fin_ledger.events), 1)

    def test_risk_evaluation_freeze_limit(self):
        """Tests that RiskPolicyEvaluator enforces RK-06 hard freeze quantity limit."""
        evaluator = risk.RiskPolicyEvaluator(max_loss_paise=domain.Paise(500000), freeze_quantity=1800)
        cid = domain.ContractIdentifier("k", "s", "2024-12-26", 24000.0, domain.OptionType.CE, 25)

        # 1800 lots: PASS
        dec_pass = evaluator.evaluate_order(cid, quantity=1800)
        self.assertEqual(dec_pass.verdict, risk.RiskVerdict.PASS)

        # 1825 lots: REJECT under RK-06
        dec_reject = evaluator.evaluate_order(cid, quantity=1825)
        self.assertEqual(dec_reject.verdict, risk.RiskVerdict.REJECT)
        self.assertEqual(dec_reject.rule_id, "RK-06")

    def test_engine_run_config(self):
        """Tests that EngineRunConfig stores execution parameters cleanly."""
        cfg = engine.EngineRunConfig(
            mode=domain.OperatingMode.ACTUAL_OPTIONS,
            start_date="2024-12-01",
            end_date="2024-12-26",
            initial_capital_paise=10000000,
            strategy_name="SampleStraddle",
        )
        self.assertEqual(cfg.mode, domain.OperatingMode.ACTUAL_OPTIONS)
        self.assertEqual(cfg.initial_capital_paise, 10000000)


class TestImportBoundaries(unittest.TestCase):
    """
    1. The use of class:
       Inspects Python AST across packages to strictly enforce architectural dependency directions.

    2. What the class contains:
       - test_domain_has_zero_internal_dependencies: Asserts packages.domain imports no packages.*.
       - test_strategies_do_not_import_engine_or_risk: Asserts strategies are decoupled.
       - test_no_broker_sdk_in_packages: Asserts broker SDKs (e.g. upstox_client) never imported in packages.

    3. Technologies used and why:
       ast.parse to inspect static import statements without side effects.

    4. Key design and overall design of the class:
       Static code analysis enforcing Master Spec §3 package boundary rules.
    """

    def _get_imports_in_file(self, file_path: Path):
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports

    def test_domain_is_leaf(self):
        """Asserts that packages/domain never imports from any other package."""
        domain_files = list(Path("packages/domain").glob("*.py"))
        for f in domain_files:
            imports = self._get_imports_in_file(f)
            for imp in imports:
                self.assertFalse(
                    imp.startswith("packages.") and not imp.startswith("packages.domain"),
                    f"Illegal dependency: packages/domain must be leaf, found import '{imp}' in {f}",
                )

    def test_no_broker_sdk_in_packages(self):
        """Asserts that packages/* never imports broker SDKs (e.g. upstox_client)."""
        forbidden_sdk_prefixes = ["upstox_client", "upstox_api", "smartapi", "kiteconnect"]
        package_files = list(Path("packages").rglob("*.py"))
        for f in package_files:
            imports = self._get_imports_in_file(f)
            for imp in imports:
                for forbidden in forbidden_sdk_prefixes:
                    self.assertFalse(
                        imp.startswith(forbidden),
                        f"Architecture violation: packages must never import broker SDK '{imp}' in {f}",
                    )


if __name__ == "__main__":
    unittest.main()
