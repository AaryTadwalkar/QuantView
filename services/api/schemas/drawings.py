"""
1. What this file does:
   Defines Pydantic data schemas for chart drawings, annotations, coordinates, and persistence operations
   in the QuantView Gateway (Milestone M6-13, Gate G4).

2. Overall design:
   Provides strongly typed models for TradingView Lightweight Charts custom drawing primitives:
     - DrawingPoint: Two-dimensional chart coordinate comprising UTC epoch seconds and price.
     - DrawingRecord: Complete user drawing entity with tool type, points array, and visual styling properties.
     - DrawingDeleteResponse: Confirmation payload for single or bulk drawing deletions.

3. Elements in the file:
   - DrawingPoint: Coordinate point representation schema.
   - DrawingRecord: Persistent chart drawing annotation schema.
   - DrawingDeleteResponse: Deletion confirmation result schema.

4. Final output of the file:
   - Exported Pydantic schemas for chart drawing persistence and REST CRUD operations.
"""

import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DrawingPoint(BaseModel):
    """
    1. The use of class:
       Represents an individual anchor coordinate on the chart canvas.

    2. What the class contains:
       - time: Horizontal axis coordinate expressed as UTC epoch seconds.
       - price: Vertical axis coordinate expressed as float price level.

    3. Technologies used and why:
       Pydantic BaseModel for deterministic serialization aligned with Lightweight Charts coordinate systems.

    4. Key design and overall design of the class:
       Provides atomic (time, price) tuple semantics supporting 1-point, 2-point, and multi-point geometries.
    """

    time: int = Field(description="Point time coordinate in UTC epoch seconds")
    price: float = Field(description="Point price coordinate on vertical axis")


class DrawingRecord(BaseModel):
    """
    1. The use of class:
       Data model for user-created chart drawing annotations stored in memory and persisted to disk.

    2. What the class contains:
       - id: Unique drawing identifier string (UUID).
       - symbol: Target instrument symbol associated with this drawing.
       - type: Drawing tool type string ('trendline', 'horizontal_line', 'rectangle', 'long', 'short', 'fibonacci', 'measure').
       - points: List of DrawingPoint anchor coordinates.
       - properties: Arbitrary styling parameters (color, line width, transparency, labels, fill).
       - created_at: Creation timestamp in epoch seconds.
       - updated_at: Last update timestamp in epoch seconds.

    3. Technologies used and why:
       Pydantic BaseModel with factory defaults for UUID generation and timestamp tracking.

    4. Key design and overall design of the class:
       Enforces lossless drawing persistence and multi-device chart state synchronization.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique drawing record identifier",
    )
    symbol: str = Field(description="Target instrument symbol (e.g. NSE:NIFTY50, NIFTY)")
    type: str = Field(
        description="Drawing tool type (e.g. 'trendline', 'horizontal_line', 'rectangle', 'fibonacci')",
    )
    points: List[DrawingPoint] = Field(
        default_factory=list,
        description="List of anchor points defining the drawing geometry",
    )
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Visual appearance attributes (colors, line width, fill, text)",
    )
    created_at: int = Field(
        default_factory=lambda: int(time.time()),
        description="Creation timestamp in UTC epoch seconds",
    )
    updated_at: int = Field(
        default_factory=lambda: int(time.time()),
        description="Last modified timestamp in UTC epoch seconds",
    )


class DrawingDeleteResponse(BaseModel):
    """
    1. The use of class:
       Response data transfer object returned upon successful deletion of one or more drawings.

    2. What the class contains:
       - status: Operation outcome status (always 'deleted').
       - id: Optional identifier of the specifically deleted drawing.
       - symbol: Optional instrument symbol if drawings were purged in bulk.
       - count: Optional count of purged drawing entities.

    3. Technologies used and why:
       Pydantic BaseModel for typed REST deletion confirmation responses.

    4. Key design and overall design of the class:
       Supports both single-resource and collection-level deletion confirmations.
    """

    status: str = Field(default="deleted", description="Operation status string")
    id: Optional[str] = Field(default=None, description="Deleted drawing identifier")
    symbol: Optional[str] = Field(default=None, description="Target symbol if bulk deleted")
    count: Optional[int] = Field(default=None, description="Count of drawings removed")
