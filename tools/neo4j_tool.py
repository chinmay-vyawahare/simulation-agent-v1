"""
Neo4j Knowledge Graph tools for the Traversal Agent.
Handles connection, schema discovery, and query execution.
"""
from __future__ import annotations

import time
import logging
from typing import Any, Optional

from neo4j import GraphDatabase, Driver

from config.settings import config

logger = logging.getLogger(__name__)


class Neo4jTool:
    """Manages Neo4j connections and query execution."""

    def __init__(self):
        self._driver: Optional[Driver] = None

    @property
    def driver(self) -> Driver:
        if self._driver is None:
            cfg = config.neo4j
            self._driver = GraphDatabase.driver(
                cfg.uri,
                auth=(cfg.user, cfg.password),
            )
            # Verify connectivity
            self._driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {cfg.uri}, db={cfg.database}")
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    # ─────────────────────────────────────────────
    # Schema Discovery
    # ─────────────────────────────────────────────

    def get_schema(self) -> str:
        """
        Discover the knowledge graph schema: node labels, relationship types,
        and property keys. Returns a formatted string for the LLM context.
        """
        db = config.neo4j.database

        with self.driver.session(database=db) as session:
            # Node labels + properties
            node_info = session.run(
                "CALL db.schema.nodeTypeProperties() "
                "YIELD nodeType, propertyName, propertyTypes "
                "RETURN nodeType, collect({name: propertyName, types: propertyTypes}) as properties"
            ).data()

            # Relationship types + properties
            rel_info = session.run(
                "CALL db.schema.relTypeProperties() "
                "YIELD relType, propertyName, propertyTypes "
                "RETURN relType, collect({name: propertyName, types: propertyTypes}) as properties"
            ).data()

            # Sample counts per label
            label_counts = session.run(
                "CALL db.labels() YIELD label "
                "CALL { WITH label "
                "  MATCH (n) WHERE label IN labels(n) "
                "  RETURN count(n) AS cnt "
                "} "
                "RETURN label, cnt ORDER BY cnt DESC LIMIT 30"
            ).data()

            # Relationship patterns (source)-[rel]->(target)
            patterns = session.run(
                "CALL db.schema.visualization() "
                "YIELD nodes, relationships "
                "RETURN nodes, relationships"
            ).data()

        schema_lines = ["=== KNOWLEDGE GRAPH SCHEMA ===\n"]

        schema_lines.append("── Node Labels & Properties ──")
        for row in node_info:
            props = ", ".join(
                f"{p['name']}:{'/'.join(p['types'])}"
                for p in row["properties"] if p["name"]
            )
            schema_lines.append(f"  {row['nodeType']}  →  {props or '(no properties)'}")

        schema_lines.append("\n── Node Counts ──")
        for row in label_counts:
            schema_lines.append(f"  :{row['label']}  →  {row['cnt']} nodes")

        schema_lines.append("\n── Relationship Types & Properties ──")
        for row in rel_info:
            props = ", ".join(
                f"{p['name']}:{'/'.join(p['types'])}"
                for p in row["properties"] if p["name"]
            )
            schema_lines.append(f"  {row['relType']}  →  {props or '(no properties)'}")

        return "\n".join(schema_lines)

    # ─────────────────────────────────────────────
    # Query Execution
    # ─────────────────────────────────────────────

    def run_cypher(self, query: str, params: dict[str, Any] | None = None) -> dict:
        """
        Execute a Cypher query and return results + metadata.
        """
        db = config.neo4j.database
        params = params or {}

        start = time.perf_counter()
        try:
            with self.driver.session(database=db) as session:
                result = session.run(query, params)
                records = [record.data() for record in result]
                summary = result.consume()

            elapsed_ms = (time.perf_counter() - start) * 1000

            return {
                "status": "success",
                "records": records,
                "count": len(records),
                "elapsed_ms": round(elapsed_ms, 2),
                "query": query,
            }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(f"Cypher error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "elapsed_ms": round(elapsed_ms, 2),
                "query": query,
                "records": [],
                "count": 0,
            }

    def run_cypher_safe(self, query: str, params: dict[str, Any] | None = None) -> dict:
        """
        Execute a read-only Cypher query (rejects writes).
        """
        # Basic write-guard
        upper = query.upper().strip()
        write_keywords = ["CREATE", "MERGE", "DELETE", "DETACH", "SET ", "REMOVE "]
        for kw in write_keywords:
            if kw in upper and not upper.startswith("//"):
                return {
                    "status": "error",
                    "error": f"Write operations not allowed. Detected: {kw.strip()}",
                    "records": [],
                    "count": 0,
                    "query": query,
                }
        return self.run_cypher(query, params)


# Singleton
neo4j_tool = Neo4jTool()
