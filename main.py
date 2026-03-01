"""
CLI entry point for the Simulation Agent system.

Usage:
    python -m simulation_agent.main "Complete 300 sites in Chicago in 2 weeks"
    python -m simulation_agent.main --interactive
"""
from __future__ import annotations

import sys
import json
import logging
import argparse
from datetime import datetime

from graph import run_simulation
from tools.neo4j_tool import neo4j_tool

# ── Logging setup ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-30s │ %(levelname)-5s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║              🎯 SIMULATION AGENT (Prototype)                ║
║     LangGraph Multi-Agent System with Neo4j BKG             ║
╚══════════════════════════════════════════════════════════════╝
    """)


def print_result(state: dict):
    """Pretty-print the simulation result."""
    print("\n" + "═" * 60)
    print("  📊 SIMULATION RESULT")
    print("═" * 60)

    # Final response
    if state.get("final_response"):
        print(f"\n{state['final_response']}")

    # Calculation trace
    if state.get("calculations"):
        print("\n── Calculation Trace ──")
        print(state["calculations"])

    # Execution trace
    print("\n── Execution Trace ──")
    messages = state.get("messages", [])
    for msg in messages:
        agent = msg.get("agent", "?")
        content = msg.get("content", "")
        print(f"  [{agent:>20}] {content}")

    # Errors
    errors = state.get("errors", [])
    if errors:
        print("\n── Errors ──")
        for err in errors:
            print(f"  ⚠️  {err}")

    print("\n" + "═" * 60)


def run_interactive():
    """Interactive REPL mode."""
    print_banner()
    print("Type your simulation query (or 'quit' to exit, 'schema' to see KG schema)\n")

    while True:
        try:
            query = input("🎤 Query: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break
        if query.lower() == "schema":
            try:
                schema = neo4j_tool.get_schema()
                print(schema)
            except Exception as e:
                print(f"Error: {e}")
            continue

        try:
            state = run_simulation(query)
            print_result(state)
        except Exception as e:
            logger.exception("Simulation failed")
            print(f"\n❌ Error: {e}")

    neo4j_tool.close()


def run_single(query: str):
    """Run a single query and exit."""
    print_banner()
    print(f"🎤 Query: {query}\n")

    try:
        state = run_simulation(query)
        print_result(state)
    except Exception as e:
        logger.exception("Simulation failed")
        print(f"\n❌ Error: {e}")
    finally:
        neo4j_tool.close()


def main():
    parser = argparse.ArgumentParser(description="Simulation Agent CLI")
    parser.add_argument("query", nargs="?", help="Simulation query to run")
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive REPL mode",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Print the knowledge graph schema and exit",
    )

    args = parser.parse_args()

    if args.schema:
        try:
            schema = neo4j_tool.get_schema()
            print(schema)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            neo4j_tool.close()
        return

    if args.interactive or not args.query:
        run_interactive()
    else:
        run_single(args.query)


if __name__ == "__main__":
    main()
