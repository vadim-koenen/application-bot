from __future__ import annotations

from pathlib import Path
from typing import Any

from application_bot.pipeline import run_dry_pipeline


def scheduler_status(config: dict[str, Any]) -> dict[str, Any]:
    scheduler = config.get("scheduler", {})
    return {
        "enabled": bool(scheduler.get("enabled", False)),
        "cadence": scheduler.get("cadence", "daily"),
        "time": scheduler.get("time", "08:00"),
        "timezone": scheduler.get("timezone", "America/Chicago"),
        "installed": False,
        "running": False,
    }


def run_scheduler_once(
    *,
    config: dict[str, Any],
    registry_path: str | Path,
    database_path: str | Path,
    output_root: str | Path,
    limit: int = 25,
    adapters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = run_dry_pipeline(
        database_path=database_path,
        registry_path=registry_path,
        output_root=output_root,
        config=config,
        limit=limit,
        adapters=adapters,
    )
    return {
        "scheduler": {
            **scheduler_status(config),
            "run_once": True,
        },
        "pipeline": result,
    }
