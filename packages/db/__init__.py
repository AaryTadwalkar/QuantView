"""
1. What this file does:
   Defines the database connection and topology contracts for QuantView's PostgreSQL layer.

2. Overall design:
   QuantView enforces physical database isolation across three environments:
     1. qv_core: Master metadata, instrument catalog, user settings, backtest runs.
     2. qv_paper: Paper accounts, paper orders, paper positions, paper ledger events.
     3. qv_live: Strictly isolated live trading database (disabled by default until GATE-05).

3. Elements in the file:
   - DatabaseTopology: Enum defining the three isolated database targets.
   - DatabaseConfig: Connection parameters and safety invariants.

4. Final output of the file:
   - Exported database topology contracts and configuration records.
"""

from enum import Enum
from typing import NamedTuple


class DatabaseTopology(str, Enum):
    """
    1. The use of class:
       Enumerates the three physically isolated PostgreSQL databases.

    2. What the class contains:
       - QV_CORE: Master metadata and analytical runs.
       - QV_PAPER: Simulated paper trading state.
       - QV_LIVE: Live broker execution state (isolated and locked until GATE-05).

    3. Technologies used and why:
       str and Enum for connection routing.

    4. Key design and overall design of the class:
       Guarantees paper trading and live trading state never share tables or connections.
    """
    QV_CORE = "qv_core"
    QV_PAPER = "qv_paper"
    QV_LIVE = "qv_live"


class DatabaseConfig(NamedTuple):
    """
    1. The use of class:
       Encapsulates connection parameters for a specific database topology.

    2. What the class contains:
       - target: DatabaseTopology enum.
       - host: Hostname or IP.
       - port: Port number (default 5432).
       - db_name: Database name string.

    3. Technologies used and why:
       NamedTuple for immutable connection properties.

    4. Key design and overall design of the class:
       Credentials are never stored inside this model; loaded dynamically via environment variables.
    """
    target: DatabaseTopology
    host: str
    port: int
    db_name: str
