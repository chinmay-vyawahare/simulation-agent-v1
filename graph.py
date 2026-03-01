"""
Simulation Agent — Main LangGraph definition.

Assembles the Orchestrator → Planner → Traversal → Response pipeline
with conditional edges for re-planning on failures.

Graph Flow:
    START → discover_schema → planner → traversal → orchestrator
                ↑                                        ↓
                └──── (re-plan) ─────────────────────────┘
                                                         ↓
                                                     response → END
"""
from __future__ import annotations

import logging
from datetime import datetime

from langgraph.graph import StateGraph, START, END

from models.state import SimulationState
from agents.schema_discovery import discover_schema_node
from agents.planner import planner_node
from agents.traversal import traversal_node
from agents.orchestrator import orchestrator_node, route_after_orchestrator
from agents.response import response_node

logger = logging.getLogger(__name__)


def build_simulation_graph() -> StateGraph:
    """
    Build and compile the LangGraph for the simulation agent system.

    Returns a compiled graph that can be invoked with a SimulationState.
    """

    # ── Define the graph ──
    graph = StateGraph(SimulationState)

    # ── Add nodes ──
    graph.add_node("discover_schema", discover_schema_node)
    graph.add_node("planner", planner_node)
    graph.add_node("traversal", traversal_node)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("response", response_node)

    # ── Add edges ──

    # START → schema discovery
    graph.add_edge(START, "discover_schema")

    # Schema discovery → planner (always)
    graph.add_edge("discover_schema", "planner")

    # Planner → traversal (always, after creating plan)
    graph.add_edge("planner", "traversal")

    # Traversal → orchestrator (always, for evaluation)
    graph.add_edge("traversal", "orchestrator")

    # Orchestrator → conditional routing
    graph.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "planning": "planner",     # Re-plan on failures
            "response": "response",    # Proceed to response
            "error": "response",       # Error → still generate response with what we have
            "complete": END,
        },
    )

    # Response → END
    graph.add_edge("response", END)

    # ── Compile ──
    compiled = graph.compile()
    logger.info("Simulation graph compiled successfully")

    return compiled


def run_simulation(query: str) -> dict:
    """
    Convenience function: run a simulation query end-to-end.

    Args:
        query: The user's simulation question (e.g., "Complete 300 sites in Chicago in 2 weeks")

    Returns:
        The final state dict with all results.
    """
    graph = build_simulation_graph()

    initial_state: SimulationState = {
        "user_query": query,
        "current_phase": "planning",
        "iteration": 0,
        "plan": [],
        "plan_reasoning": "",
        "kg_schema": "",
        "execution_results": [],
        "pending_steps": [],
        "final_response": "",
        "calculations": "",
        "data_summary": {},
        "errors": [],
        "created_at": datetime.now().isoformat(),
        "messages": [],
    }

    logger.info(f"Starting simulation for: {query}")
    final_state = graph.invoke(initial_state)
    logger.info("Simulation complete")

    return final_state
