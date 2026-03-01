"""
Traversal Agent — Executes plan steps against the Neo4j knowledge graph
and Python sandbox. Handles retries and error recovery.
"""
from __future__ import annotations

import json
import time
import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import config
from models.state import SimulationState, ExecutionResult
from tools.neo4j_tool import neo4j_tool
from tools.python_sandbox import execute_python
from prompts.agent_prompts import TRAVERSAL_SYSTEM

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


def _fix_cypher_with_llm(
    original_query: str, error: str, schema: str
) -> str:
    """Ask the LLM to fix a broken Cypher query."""
    llm = ChatOpenAI(
        model=config.llm.model,
        temperature=0,
        max_tokens=1024,
    )
    response = llm.invoke([
        SystemMessage(content=(
            "You are a Neo4j Cypher expert. Fix the following query based on "
            "the error message and schema. Return ONLY the corrected Cypher query, "
            "no explanation.\n\n"
            f"## Schema\n{schema}"
        )),
        HumanMessage(content=(
            f"## Original Query\n```\n{original_query}\n```\n\n"
            f"## Error\n{error}\n\n"
            "Return ONLY the fixed Cypher query."
        )),
    ])
    return response.content.strip().strip("`").strip()


def _execute_cypher_step(
    step: dict, schema: str
) -> ExecutionResult:
    """Execute a Cypher query step with retry logic."""
    query = step["query_or_code"]
    start = time.perf_counter()

    for attempt in range(MAX_RETRIES + 1):
        result = neo4j_tool.run_cypher_safe(query)

        if result["status"] == "success":
            elapsed = (time.perf_counter() - start) * 1000
            return ExecutionResult(
                step_id=step["step_id"],
                status="success",
                data=result["records"],
                error=None,
                execution_time_ms=round(elapsed, 2),
            )

        # Try to fix on retry
        if attempt < MAX_RETRIES:
            logger.warning(
                f"Step {step['step_id']} failed (attempt {attempt + 1}): "
                f"{result['error']}. Attempting fix..."
            )
            query = _fix_cypher_with_llm(query, result["error"], schema)
            logger.info(f"Fixed query: {query[:200]}")
        else:
            elapsed = (time.perf_counter() - start) * 1000
            return ExecutionResult(
                step_id=step["step_id"],
                status="error",
                data=None,
                error=result["error"],
                execution_time_ms=round(elapsed, 2),
            )


def _execute_python_step(
    step: dict, prior_results: dict[int, Any]
) -> ExecutionResult:
    """Execute a Python computation step."""
    code = step["query_or_code"]
    start = time.perf_counter()

    # Build context from dependent steps
    context = {}
    for dep_id in step.get("depends_on", []):
        if dep_id in prior_results:
            context[f"step_{dep_id}_data"] = prior_results[dep_id]

    result = execute_python(code, context)
    elapsed = (time.perf_counter() - start) * 1000

    if result["status"] == "success":
        return ExecutionResult(
            step_id=step["step_id"],
            status="success",
            data=result.get("result") or result.get("output", ""),
            error=None,
            execution_time_ms=round(elapsed, 2),
        )
    else:
        return ExecutionResult(
            step_id=step["step_id"],
            status="error",
            data=None,
            error=result.get("error", "Unknown error"),
            execution_time_ms=round(elapsed, 2),
        )


def _execute_aggregate_step(
    step: dict, prior_results: dict[int, Any]
) -> ExecutionResult:
    """Aggregate results from multiple prior steps."""
    start = time.perf_counter()

    aggregated = {}
    for dep_id in step.get("depends_on", []):
        if dep_id in prior_results:
            aggregated[f"step_{dep_id}"] = prior_results[dep_id]

    elapsed = (time.perf_counter() - start) * 1000
    return ExecutionResult(
        step_id=step["step_id"],
        status="success",
        data=aggregated,
        error=None,
        execution_time_ms=round(elapsed, 2),
    )


def traversal_node(state: SimulationState) -> dict[str, Any]:
    """
    LangGraph node: Traversal Agent.

    Reads: plan, pending_steps, kg_schema, execution_results
    Writes: execution_results, pending_steps, current_phase, messages
    """
    plan = state.get("plan", [])
    schema = state.get("kg_schema", "")
    prior_exec = state.get("execution_results", [])

    # Build lookup of already-executed results
    prior_results: dict[int, Any] = {}
    for r in prior_exec:
        if r["status"] == "success":
            prior_results[r["step_id"]] = r["data"]

    # Sort steps by dependency order
    pending_ids = set(state.get("pending_steps", [s["step_id"] for s in plan]))
    steps_by_id = {s["step_id"]: s for s in plan}

    new_results: list[ExecutionResult] = []
    executed_ids: set[int] = set()
    errors: list[str] = []

    # Simple topological execution
    max_iterations = len(plan) + 5  # Safety bound
    iteration = 0

    while pending_ids and iteration < max_iterations:
        iteration += 1
        progress = False

        for step_id in sorted(pending_ids):
            step = steps_by_id.get(step_id)
            if not step:
                pending_ids.discard(step_id)
                continue

            # Check dependencies are met
            deps = set(step.get("depends_on", []))
            completed_ids = set(prior_results.keys()) | executed_ids
            if not deps.issubset(completed_ids):
                continue  # Dependencies not yet met

            logger.info(
                f"Executing step {step_id}: {step['action']} — {step['description']}"
            )

            # Route to appropriate executor
            if step["action"] == "cypher_query":
                result = _execute_cypher_step(step, schema)
            elif step["action"] == "python_compute":
                # Merge prior + newly executed results
                all_results = {**prior_results}
                for r in new_results:
                    if r["status"] == "success":
                        all_results[r["step_id"]] = r["data"]
                result = _execute_python_step(step, all_results)
            elif step["action"] == "aggregate":
                all_results = {**prior_results}
                for r in new_results:
                    if r["status"] == "success":
                        all_results[r["step_id"]] = r["data"]
                result = _execute_aggregate_step(step, all_results)
            else:
                result = ExecutionResult(
                    step_id=step_id,
                    status="error",
                    data=None,
                    error=f"Unknown action: {step['action']}",
                    execution_time_ms=0,
                )

            new_results.append(result)
            pending_ids.discard(step_id)
            executed_ids.add(step_id)

            if result["status"] == "success":
                prior_results[step_id] = result["data"]
            else:
                errors.append(
                    f"Step {step_id} ({step['description']}): {result.get('error')}"
                )

            progress = True

        if not progress:
            # Deadlock — remaining steps have unmet dependencies
            for sid in pending_ids:
                errors.append(f"Step {sid}: unmet dependencies, skipped")
            break

    # Summarize
    success_count = sum(1 for r in new_results if r["status"] == "success")
    total = len(new_results)

    logger.info(f"Traversal complete: {success_count}/{total} steps succeeded")

    return {
        "execution_results": new_results,
        "pending_steps": list(pending_ids),
        "current_phase": "response",
        "errors": errors,
        "messages": [{
            "agent": "traversal",
            "content": (
                f"Executed {total} steps: {success_count} succeeded, "
                f"{total - success_count} failed"
            ),
        }],
    }
