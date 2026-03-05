"""Run trigger API routes.

Exposes a protected endpoint for manually triggering the tower assembly
workflow.  All requests must include a valid ``X-API-Key`` header.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends

from orchestrator.core.security import verify_api_key
from orchestrator.graph.workflow import build_assembly_graph
from orchestrator.schemas.tower import RunTriggerRequest, RunTriggerResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.post("/trigger/", response_model=RunTriggerResponse)
async def trigger_assembly_run(
    request: RunTriggerRequest | None = None,
    _api_key: str = Depends(verify_api_key),
) -> RunTriggerResponse:
    """Manually trigger an assembly run for the specified tiers.

    Builds and invokes the LangGraph assembly workflow, then returns a
    summary containing the hashes of newly created towers and any errors
    that occurred during the run.

    Args:
        request: Optional request body containing the list of tiers to
            assemble.  Defaults to ``["Home", "Business", "Gaming"]`` when
            not provided.
        _api_key: Validated API key injected by the ``verify_api_key``
            dependency (value not used directly).

    Returns:
        A :class:`RunTriggerResponse` with the run status, created tower
        hashes, total count, and any accumulated errors.
    """
    effective_request = request if request is not None else RunTriggerRequest()
    logger.info("Manual assembly run triggered for tiers: %s", effective_request.tiers)

    graph = build_assembly_graph()
    final_state: dict[str, Any] = await graph.ainvoke({"requested_tiers": effective_request.tiers})

    completed_builds: list[dict[str, Any]] = list(final_state.get("completed_builds", []))
    completed_bundles: list[dict[str, Any]] = list(final_state.get("completed_bundles", []))
    errors: list[str] = list(final_state.get("errors", []))
    run_status: str = str(final_state.get("run_status", "failed"))

    tower_hashes: list[str] = [
        str(build["bundle_hash"]) for build in completed_builds if build.get("bundle_hash")
    ]

    logger.info(
        "Assembly run completed — status=%s towers=%d bundles=%d errors=%d",
        run_status,
        len(tower_hashes),
        len(completed_bundles),
        len(errors),
    )

    return RunTriggerResponse(
        status=run_status,
        towers_created=len(tower_hashes),
        tower_hashes=tower_hashes,
        bundles_created=len(completed_bundles),
        errors=errors,
    )
