"""
Response Agent — Interprets traversal results, performs calculations
via Python sandbox, and generates a PM-readable response.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import config
from models.state import SimulationState
from tools.python_sandbox import execute_python
from prompts.agent_prompts import RESPONSE_SYSTEM

logger = logging.getLogger(__name__)


def _format_execution_data(state: SimulationState) -> str:
    """Format all execution results into a readable context for the LLM."""
    plan = state.get("plan", [])
    results = state.get("execution_results", [])

    # Map step_id → step info
    steps_by_id = {s["step_id"]: s for s in plan}

    # Map step_id → result
    results_by_id = {}
    for r in results:
        # Keep latest result per step (in case of retries)
        results_by_id[r["step_id"]] = r

    lines = ["## Collected Data from Knowledge Graph Traversal\n"]

    for step_id in sorted(results_by_id.keys()):
        result = results_by_id[step_id]
        step = steps_by_id.get(step_id, {})

        status_icon = "✅" if result["status"] == "success" else "❌"
        lines.append(f"### Step {step_id}: {step.get('description', 'Unknown')} {status_icon}")
        lines.append(f"**Purpose**: {step.get('purpose', 'N/A')}")
        lines.append(f"**Action**: {step.get('action', 'N/A')}")

        if result["status"] == "success" and result.get("data") is not None:
            data = result["data"]
            # Truncate large datasets
            data_str = json.dumps(data, default=str, indent=2)
            if len(data_str) > 3000:
                data_str = data_str[:3000] + "\n... (truncated)"
            lines.append(f"**Data**:\n```json\n{data_str}\n```")
        elif result.get("error"):
            lines.append(f"**Error**: {result['error']}")
        else:
            lines.append("**Data**: No results returned")

        lines.append("")

    return "\n".join(lines)


def response_node(state: SimulationState) -> dict[str, Any]:
    """
    LangGraph node: Response Agent.

    Reads: user_query, plan, execution_results, plan_reasoning
    Writes: final_response, calculations, data_summary, current_phase, messages
    """
    llm = ChatOpenAI(
        model=config.llm.model,
        temperature=0.1,  # Slight creativity for presentation
        max_tokens=config.llm.max_tokens,
    )

    # Build context
    data_context = _format_execution_data(state)
    errors = state.get("errors", [])

    user_message_parts = [
        f"## Original User Query\n{state['user_query']}",
        f"\n## Plan Reasoning\n{state.get('plan_reasoning', 'N/A')}",
        f"\n{data_context}",
    ]

    if errors:
        user_message_parts.append(
            "\n## Errors Encountered\n" +
            "\n".join(f"- {e}" for e in errors)
        )

    user_message_parts.append(
        "\n## Instructions"
        "\nAnalyze the collected data above and generate a comprehensive, "
        "PM-readable response. Use Python sandbox for any calculations — "
        "write the code and I'll execute it. Include specific numbers from "
        "the data. If data is missing or queries failed, acknowledge it explicitly."
    )

    user_message = "\n".join(user_message_parts)

    # Call LLM
    response = llm.invoke([
        SystemMessage(content=RESPONSE_SYSTEM),
        HumanMessage(content=user_message),
    ])

    final_response = response.content

    # Try to extract any Python calculation blocks and execute them
    calculations_output = ""
    if "```python" in final_response:
        code_blocks = final_response.split("```python")
        for block in code_blocks[1:]:
            code = block.split("```")[0].strip()
            if code:
                # Build context from execution results
                exec_context = {}
                for r in state.get("execution_results", []):
                    if r["status"] == "success":
                        exec_context[f"step_{r['step_id']}_data"] = r["data"]

                calc_result = execute_python(code, exec_context)
                if calc_result["status"] == "success":
                    output = calc_result.get("output", "")
                    result_val = calc_result.get("result")
                    calculations_output += (
                        f"Calculation:\n{code}\n"
                        f"Output: {output}\n"
                        f"Result: {result_val}\n\n"
                    )

    # Build data summary from successful results
    data_summary = {}
    for r in state.get("execution_results", []):
        if r["status"] == "success" and r.get("data"):
            data_summary[f"step_{r['step_id']}"] = r["data"]

    logger.info("Response agent generated final output")

    return {
        "final_response": final_response,
        "calculations": calculations_output,
        "data_summary": data_summary,
        "current_phase": "complete",
        "messages": [{
            "agent": "response",
            "content": "Generated final response",
        }],
    }
