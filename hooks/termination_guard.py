#!/usr/bin/env python3

"""Provider-independent crash-boundary catalog adjudication fixture."""

from __future__ import annotations

from collections.abc import Callable, Mapping


class TerminationViolation(RuntimeError):
    pass


REPORT_FIELDS = {
    "boundary_id",
    "termination_primitive",
    "terminated_pid",
    "observer_pid",
    "durable_resolution",
}


def adjudicate_boundary_catalog(
    termination_contract: Mapping[str, object],
    *,
    observe_boundary: Callable[[Mapping[str, object]], Mapping[str, object]],
) -> dict:
    """Run one owner-internal observer for every entry in the closed catalog."""
    if termination_contract.get("catalog_closed") is not True:
        raise TerminationViolation("termination boundary catalog is not closed")
    catalog = termination_contract.get("boundary_catalog")
    if not isinstance(catalog, list):
        raise TerminationViolation("termination boundary catalog is invalid")
    boundary_ids = [item.get("boundary_id") for item in catalog]
    if len(set(boundary_ids)) != len(boundary_ids):
        raise TerminationViolation("termination boundary catalog contains duplicates")
    for boundary in catalog:
        boundary_id = boundary["boundary_id"]
        report = observe_boundary(boundary)
        if not isinstance(report, Mapping):
            raise TerminationViolation(f"owner observer returned no report for {boundary_id}")
        if set(report) != REPORT_FIELDS:
            raise TerminationViolation(f"crash report fields are not exact for {boundary_id}")
        if report["boundary_id"] != boundary_id:
            raise TerminationViolation(f"owner observer returned the wrong boundary for {boundary_id}")
        if report["termination_primitive"] != boundary["termination_primitive"]:
            raise TerminationViolation(f"termination primitive mismatch for {boundary_id}")
        if report["termination_primitive"] != "os._exit":
            raise TerminationViolation(f"crash report did not use process-death semantics for {boundary_id}")
        if (
            type(report["terminated_pid"]) is not int
            or type(report["observer_pid"]) is not int
            or report["terminated_pid"] == report["observer_pid"]
        ):
            raise TerminationViolation(f"durable resolution was not observed by a fresh process for {boundary_id}")
        if report["durable_resolution"] != boundary["expected_durable_resolution"]:
            raise TerminationViolation(f"durable resolution mismatch for {boundary_id}")
    return {"catalog_complete": True, "boundary_count": len(catalog)}
