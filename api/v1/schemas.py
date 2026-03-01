"""
Pydantic request / response schemas for the v1 API.

All models live here so endpoints stay thin and types are reusable.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


# ── Simulate ──────────────────────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    query: str

    model_config = {
        "json_schema_extra": {
            "example": {"query": "How many active GC sites are in Chicago?"}
        }
    }


class SimulateResponse(BaseModel):
    final_response: str
    data_summary:   dict[str, Any]
    calculations:   str
    errors:         list[str]
    messages:       list[dict[str, Any]]
    iteration:      int


# ── BKG ───────────────────────────────────────────────────────────────────────

class BKGQueryRequest(BaseModel):
    mode:       str
    node_id:    Optional[str] = None
    metric_id:  Optional[str] = None
    question:   Optional[str] = None
    start:      Optional[str] = None
    depth:      Optional[int] = 2
    rel_type:   Optional[str] = None
    table_name: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"mode": "get_node",      "node_id": "GeneralContractor"},
                {"mode": "find_relevant", "question": "contractor project site"},
                {"mode": "traverse",      "start": "GeneralContractor", "depth": 2},
                {"mode": "diagnostic",    "metric_id": "completion_rate"},
                {"mode": "schema"},
            ]
        }
    }


# ── Sandbox ───────────────────────────────────────────────────────────────────

class SandboxRequest(BaseModel):
    code:            str
    timeout_seconds: int = 30

    model_config = {
        "json_schema_extra": {
            "example": {
                "code": (
                    "df = pd.read_sql('SELECT 1 AS test', conn)\n"
                    "result = {'data': df.to_dict(orient='records')}"
                ),
                "timeout_seconds": 30,
            }
        }
    }
