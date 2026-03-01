"""
Planner Agent — Decomposes the user query into a sequence of
executable steps (Cypher queries, Python computations) based on
the knowledge graph schema.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import config
from models.state import SimulationState, PlanStep
from prompts.agent_prompts import PLANNER_SYSTEM

logger = logging.getLogger(__name__)


def planner_node(state: SimulationState) -> dict[str, Any]:
    """
    LangGraph node: Planner Agent.

    Reads: user_query, kg_schema, execution_results (if re-planning)
    Writes: plan, plan_reasoning, pending_steps, messages
    """
    llm = ChatOpenAI(
        model=config.llm.model,
        temperature=config.llm.temperature,
        max_tokens=config.llm.max_tokens,
    )

    # Format system prompt with schema
    system_prompt = PLANNER_SYSTEM.format(
        kg_schema=state.get("kg_schema", "Schema not yet discovered")
    )

    # Build user message
    user_msg_parts = [f"## User Query\n{state['user_query']}"]

    # If re-planning, include prior results context
    prior_results = state.get("execution_results", [])
    if prior_results:
        user_msg_parts.append("\n## Previous Execution Results (for context)")
        for res in prior_results:
            status_icon = "✅" if res["status"] == "success" else "❌"
            user_msg_parts.append(
                f"  Step {res['step_id']}: {status_icon} {res['status']}"
            )
            if res["status"] == "success" and res.get("data"):
                data_preview = json.dumps(res["data"], default=str)[:500]
                user_msg_parts.append(f"    Data: {data_preview}")
            if res.get("error"):
                user_msg_parts.append(f"    Error: {res['error']}")

    # If orchestrator sent feedback
    iteration = state.get("iteration", 0)
    if iteration > 0:
        user_msg_parts.append(
            f"\n## Re-planning (iteration {iteration})"
            "\nPrevious plan had issues. Create an improved plan using the "
            "results and errors from prior execution."
        )

    user_message = "\n".join(user_msg_parts)

    # Call LLM
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ])

    # Parse response
    try:
        # Extract JSON from response (handle markdown code blocks)
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        plan_data = json.loads(content)
        steps: list[PlanStep] = plan_data.get("steps", [])
        reasoning = plan_data.get("reasoning", "")

        logger.info(f"Planner created {len(steps)} steps")

        return {
            "plan": steps,
            "plan_reasoning": reasoning,
            "pending_steps": [s["step_id"] for s in steps],
            "current_phase": "traversal",
            "messages": [{
                "agent": "planner",
                "content": f"Created plan with {len(steps)} steps: {reasoning[:200]}",
            }],
        }

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Planner failed to parse response: {e}")
        return {
            "plan": [],
            "plan_reasoning": f"Error parsing plan: {e}",
            "pending_steps": [],
            "current_phase": "error",
            "errors": [f"Planner parse error: {e}\nRaw response: {response.content[:500]}"],
            "messages": [{
                "agent": "planner",
                "content": f"Failed to create plan: {e}",
            }],
        }
