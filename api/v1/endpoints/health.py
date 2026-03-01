"""
Health endpoint — GET /api/v1/health

Delegates connectivity checks to the service layer.
No business logic lives here.
"""
from fastapi import APIRouter

import services.bkg_service     as bkg_svc
import services.sandbox_service as sandbox_svc

router = APIRouter(tags=["System"])


@router.get("/health")
def health_check():
    """Check connectivity to Neo4j and PostgreSQL."""
    neo4j   = bkg_svc.health()
    postgres = sandbox_svc.health()

    overall = (
        "ok"
        if neo4j["status"] == "connected" or postgres["status"] == "connected"
        else "degraded"
    )
    return {
        "status":   overall,
        "neo4j":    neo4j["status"],
        "postgres": postgres["status"],
    }
