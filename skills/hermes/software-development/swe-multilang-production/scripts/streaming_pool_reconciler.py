#!/usr/bin/env python3
"""Plan one Hermes streaming-subagent reconciliation cycle from a JSON snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ACTIVE = {"running", "starting"}
TERMINAL = {"completed", "failed", "exited"}


def reconcile(snapshot: dict[str, Any], target_active: int = 10) -> dict[str, Any]:
    if target_active < 1:
        raise ValueError("target_active must be positive")
    agents = snapshot.get("agents")
    runnable = snapshot.get("runnable")
    frozen_lanes = set(snapshot.get("frozen_lanes") or [])
    if not isinstance(agents, list) or not isinstance(runnable, list):
        raise ValueError("snapshot requires agents and runnable lists")

    active = [row for row in agents if row.get("status") in ACTIVE]
    terminal = [row for row in agents if row.get("status") in TERMINAL]
    unknown = [row for row in agents if row.get("status") not in ACTIVE | TERMINAL]
    if unknown:
        raise ValueError("unknown agent status: " + ",".join(str(x.get("status")) for x in unknown))

    active_agent_ids = [str(row.get("agent_id") or "") for row in active]
    active_task_ids = [str(row.get("task_id") or "") for row in active]
    if any(not value for value in active_agent_ids + active_task_ids):
        raise ValueError("active agents require agent_id and task_id")
    if len(set(active_agent_ids)) != len(active_agent_ids):
        raise ValueError("duplicate active agent_id")
    if len(set(active_task_ids)) != len(active_task_ids):
        raise ValueError("duplicate active task assignment")

    inheritance: dict[str, list[str]] = {}
    reap = []
    advance = []
    retry = []
    for row in terminal:
        task_id = str(row.get("task_id") or "")
        agent_id = str(row.get("agent_id") or "")
        artifacts = [str(value) for value in (row.get("artifact_paths") or []) if str(value)]
        if task_id and artifacts:
            inheritance.setdefault(task_id, []).extend(artifacts)
        reap.append({
            "agent_id": agent_id,
            "task_id": task_id,
            "status": row["status"],
            "artifact_paths": artifacts,
            "exit_reason": row.get("exit_reason"),
        })
        if row["status"] == "completed":
            advance.append({"task_id": task_id, "artifact_paths": artifacts})
        elif row.get("retry_authorized") is True and str(row.get("next_hypothesis") or "").strip():
            retry.append({
                "task_id": task_id,
                "stage": row.get("stage"),
                "lane": row.get("lane"),
                "priority": int(row.get("priority") or 0) + 1_000_000,
                "next_hypothesis": row["next_hypothesis"],
            })

    candidates = retry + list(runnable)
    candidates.sort(key=lambda row: (-int(row.get("priority") or 0), str(row.get("task_id") or "")))
    seen = set(active_task_ids)
    dispatch = []
    slots = max(0, target_active - len(active))
    for row in candidates:
        task_id = str(row.get("task_id") or "")
        lane = str(row.get("lane") or "default")
        if not task_id or task_id in seen or lane in frozen_lanes:
            continue
        seen.add(task_id)
        dispatch.append({
            "task_id": task_id,
            "stage": row.get("stage"),
            "lane": lane,
            "inherit_artifacts": sorted(set(inheritance.get(task_id, []))),
            "next_hypothesis": row.get("next_hypothesis"),
        })
        if len(dispatch) == slots:
            break

    unfilled = slots - len(dispatch)
    return {
        "schema_version": 1,
        "target_active": target_active,
        "active_before": len(active),
        "terminal_seen": len(terminal),
        "reap": reap,
        "advance_immediately": advance,
        "dispatch_immediately": dispatch,
        "active_after_planned": len(active) + len(dispatch),
        "unfilled_slots": unfilled,
        "unfilled_reason": None if unfilled == 0 else "insufficient_runnable_tasks_outside_frozen_lanes",
        "barrier_wait_forbidden": True,
        "requires_controller_action": bool(reap or advance or dispatch or unfilled),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--target-active", type=int, default=10)
    args = parser.parse_args()
    result = reconcile(json.loads(args.snapshot.read_text(encoding="utf-8")), args.target_active)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["unfilled_slots"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
