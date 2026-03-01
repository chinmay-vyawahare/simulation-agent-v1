"""
Orchestrator Agent — Coordinates the flow between Planner, Traversal,
and Response agents. Handles re-planning and error recovery.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import config
from models.state import SimulationState
from prompts.agent_prompts import ORCHESTRATOR_SYSTEM

logger = logging.getLogger(__name__)


def orchestrator_node(state: SimulationState) -> dict[str, Any]:
    """
    LangGraph node: Orchestrator Agent.

    Evaluates the current state and decides the next phase.
    This runs AFTER traversal to decide: proceed to response, or re-plan?
    """
    iteration = state.get("iteration", 0)
    exec_results = state.get("execution_results", [])
    errors = state.get("errors", [])
    plan = state.get("plan", [])

    # ── Fast-path decisions (no LLM needed) ──

    # First run → go to planning
    if not plan and iteration == 0:
        logger.info("Orchestrator: Initial run → planning")
        return {
            "current_phase": "planning",
            "iteration": 0,
            "messages": [{
                "agent": "orchestrator",
                "content": "Starting simulation — routing to Planner",
            }],
        }

    # Max iterations reached → force response
    if iteration >= 3:
        logger.info("Orchestrator: Max iterations reached → response")
        return {
            "current_phase": "response",
            "messages": [{
                "agent": "orchestrator",
                "content": "Max iterations reached. Proceeding with available data.",
            }],
        }

    # All steps succeeded → proceed to response
    success_count = sum(1 for r in exec_results if r["status"] == "success")
    total_steps = len(plan)

    if success_count == total_steps and total_steps > 0:
        logger.info(f"Orchestrator: All {total_steps} steps succeeded → response")
        return {
            "current_phase": "response",
            "messages": [{
                "agent": "orchestrator",
                "content": f"All {total_steps} steps succeeded. Generating response.",
            }],
        }

    # ── LLM decision for ambiguous cases ──

    error_count = sum(1 for r in exec_results if r["status"] == "error")

    # If most steps succeeded (>= 70%), just go to response
    if total_steps > 0 and success_count / total_steps >= 0.7:
        logger.info("Orchestrator: Majority succeeded → response with partial data")
        return {
            "current_phase": "response",
            "messages": [{
                "agent": "orchestrator",
                "content": (
                    f"{success_count}/{total_steps} steps succeeded. "
                    f"Proceeding with partial data."
                ),
            }],
        }

    # Significant failures → re-plan
    if error_count > 0 and iteration < 3:
        logger.info(f"Orchestrator: {error_count} failures → re-planning (iteration {iteration + 1})")
        return {
            "current_phase": "planning",
            "iteration": iteration + 1,
            "messages": [{
                "agent": "orchestrator",
                "content": (
                    f"{error_count} steps failed. Re-planning (iteration {iteration + 1})."
                ),
            }],
        }

    # Default: proceed to response
    return {
        "current_phase": "response",
        "messages": [{
            "agent": "orchestrator",
            "content": "Proceeding to response generation.",
        }],
    }


def route_after_orchestrator(state: SimulationState) -> str:
    """Conditional edge: route based on orchestrator's decision."""
    phase = state.get("current_phase", "planning")
    logger.info(f"Routing to: {phase}")
    return phase


def route_initial(state: SimulationState) -> str:
    """Initial routing: always start with schema discovery + planning."""
    return "discover_schema"
