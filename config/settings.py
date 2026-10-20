"""
1. What this file does:
   Defines the central configuration management and environment loading for QuantView.

2. Overall design:
   Loads environment variables securely without echoing secrets or credentials. Provides
   strongly-typed settings for paths, database targets, and runtime parameters.

3. Elements in the file:
   - QuantViewSettings: Central settings container.
   - get_settings: Factory function returning cached settings.

4. Final output of the file:
   - Configured settings instance.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv


class QuantViewSettings:
    """
    1. The use of class:
       Central runtime configuration container for QuantView.

    2. What the class contains:
       - project_root: Path to quantview workspace root.
       - data_dir: Path to Data directory.
       - staging_dir: Path to intermediate staging directory.
       - raw_dir: Path to Data/raw immutable capture root.
       - lake_dir: Path to Data/lake canonical Parquet storage.
       - pg_host: PostgreSQL hostname.
       - pg_port: PostgreSQL port number.

    3. Technologies used and why:
       Pathlib for robust filesystem path resolution.

    4. Key design and overall design of the class:
       Redacts secrets: does not expose access tokens in representation or dictionary dumps.
    """

    def __init__(self, root: Optional[Path] = None):
        """
        1. The use of function:
           Initializes QuantViewSettings from environment and defaults.

        2. How does the specific function work:
           Resolves project root and sets standard paths.

        3. Concepts used in the function:
           Configuration centralization.

        4. Places where this function is imported and used:
           Imported by services and packages.

        5. Final output of the function, before and after:
           Before: Optional root path. After: Initialized QuantViewSettings.
        """
        load_dotenv(".env")
        self.project_root = root or Path(__file__).resolve().parent.parent
        self.data_dir = self.project_root / "Data"
        self.staging_dir = self.project_root / "staging"
        self.raw_dir = self.data_dir / "raw"
        self.lake_dir = self.data_dir / "lake"
        self.pg_host = os.getenv("QV_PG_HOST", "localhost")
        self.pg_port = int(os.getenv("QV_PG_PORT", "5432"))

    def has_upstox_token(self) -> bool:
        """Returns True if UPSTOX_ACCESS_TOKEN is present and non-empty, without leaking value."""
        tok = os.getenv("UPSTOX_ACCESS_TOKEN")
        return bool(tok and tok.strip())


_settings_instance = None


def get_settings() -> QuantViewSettings:
    """
    1. The use of function:
       Singleton factory function returning the global QuantViewSettings instance.

    2. How does the specific function work:
       Instantiates QuantViewSettings on first call and caches it in module-level global.

    3. Concepts used in the function:
       Singleton pattern.

    4. Places where this function is imported and used:
       Imported by services, workers, and test suites.

    5. Final output of the function, before and after:
       Before: None. After: QuantViewSettings instance.
    """
    global _settings_instance
    if _settings_instance is None:
        from typing import Optional
        _settings_instance = QuantViewSettings()
    return _settings_instance
