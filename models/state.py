"""
Shared state models for the LangGraph simulation agent system.
All agents read/write to this shared state as it flows through the graph.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, TypedDict, Annotated
from datetime import datetime


# ─────────────────────────────────────────────
# Planner output types
# ─────────────────────────────────────────────

class PlanStep(TypedDict):
    """A single step in the execution plan."""
    step_id: int
    description: str
    action: Literal["cypher_query", "sql_query", "python_compute", "aggregate"]
    query_or_code: str  # Cypher / SQL / Python snippet
    depends_on: list[int]  # step_ids this depends on
    purpose: str  # Why this step is needed


class ExecutionResult(TypedDict):
    """Result from executing a single plan step."""
    step_id: int
    status: Literal["success", "error", "skipped"]
    data: Any  # Raw result
    error: Optional[str]
    execution_time_ms: float


# ─────────────────────────────────────────────
# Main Graph State  (shared across all nodes)
# ─────────────────────────────────────────────

class SimulationState(TypedDict):
    """
    The shared state that flows through the LangGraph.
    Uses Annotated + operator.add for list fields so that
    each node *appends* rather than overwrites.
    """
    # ── Input ──
    user_query: str

    # ── Orchestrator ──
    current_phase: Literal[
        "planning", "traversal", "response", "complete", "error"
    ]
    iteration: int  # Track re-plan cycles

    # ── Planner ──
    plan: list[PlanStep]
    plan_reasoning: str  # LLM's explanation of why this plan

    # ── Knowledge Graph Schema (discovered once) ──
    kg_schema: str  # Node labels, relationships, properties

    # ── Traversal Agent ──
    execution_results: Annotated[list[ExecutionResult], operator.add]
    pending_steps: list[int]  # step_ids not yet executed

    # ── Response Agent ──
    final_response: str
    calculations: str  # Show-your-work for transparency
    data_summary: dict[str, Any]  # Structured data for downstream sim models

    # ── Error handling ──
    errors: Annotated[list[str], operator.add]

    # ── Metadata ──
    created_at: str
    messages: Annotated[list[dict], operator.add]  # Conversation trace
