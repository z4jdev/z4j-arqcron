"""The :class:`ArqCronAdapter` - read-only scheduler adapter for
arq's ``cron_jobs``.

arq's cron jobs are configured statically in
``WorkerSettings.cron_jobs`` as a list of ``arq.cron.CronJob``
instances. They cannot be added/edited/removed at runtime - same
constraint as Huey's ``@periodic_task``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from z4j_core.models import CommandResult, Schedule, ScheduleKind

from z4j_arqcron.capabilities import DEFAULT_CAPABILITIES

logger = logging.getLogger("z4j.agent.arqcron.scheduler")

_NAME = "arq-cron"


class ArqCronAdapter:
    """Scheduler adapter for arq cron jobs.

    Args:
        cron_jobs: The same iterable you'd pass to
                   ``WorkerSettings.cron_jobs`` - each entry is an
                   ``arq.cron.CronJob`` (returned by ``arq.cron(...)``).
        project_id: Optional project id used when minting Schedule rows.
    """

    name: str = _NAME

    def __init__(
        self,
        *,
        cron_jobs: Iterable[Any],
        project_id: UUID | None = None,
    ) -> None:
        self._cron_jobs: list[Any] = list(cron_jobs)
        self._project_id = project_id or uuid4()

    def connect_signals(self, sink: Any) -> None:  # noqa: ARG002
        return

    def disconnect_signals(self) -> None:
        return

    async def list_schedules(self) -> list[Schedule]:
        out: list[Schedule] = []
        for job in self._cron_jobs:
            try:
                out.append(self._to_schedule(job))
            except Exception:  # noqa: BLE001
                logger.exception(
                    "z4j arqcron: failed to map %r",
                    getattr(job, "name", "?"),
                )
        return out

    async def get_schedule(self, schedule_id: str) -> Schedule | None:
        for s in await self.list_schedules():
            if str(s.id) == schedule_id or s.name == schedule_id:
                return s
        return None

    async def create_schedule(self, spec: Schedule) -> Schedule:  # noqa: ARG002
        raise NotImplementedError(
            "arq cron jobs are statically configured; edit your "
            "WorkerSettings.cron_jobs and redeploy.",
        )

    async def update_schedule(
        self, schedule_id: str, spec: Schedule,  # noqa: ARG002
    ) -> Schedule:
        raise NotImplementedError(
            "arq cron jobs are statically configured; edit and redeploy.",
        )

    async def delete_schedule(self, schedule_id: str) -> CommandResult:  # noqa: ARG002
        return CommandResult(
            status="failed",
            error="arq cron jobs are statically configured; remove from "
            "WorkerSettings.cron_jobs and redeploy.",
        )

    async def enable_schedule(self, schedule_id: str) -> CommandResult:  # noqa: ARG002
        return CommandResult(
            status="failed",
            error="arq cron jobs have no enable/disable toggle",
        )

    async def disable_schedule(self, schedule_id: str) -> CommandResult:  # noqa: ARG002
        return CommandResult(
            status="failed",
            error="arq cron jobs have no enable/disable toggle",
        )

    async def trigger_now(self, schedule_id: str) -> CommandResult:  # noqa: ARG002
        return CommandResult(
            status="failed",
            error=(
                "arq cron has no trigger-now primitive; enqueue the "
                "underlying coroutine via ArqRedis.enqueue_job() instead."
            ),
        )

    def capabilities(self) -> set[str]:
        return set(DEFAULT_CAPABILITIES)

    def _to_schedule(self, job: Any) -> Schedule:
        now = datetime.now(UTC)
        name = (
            getattr(job, "name", None)
            or getattr(getattr(job, "coroutine", None), "__name__", None)
            or "arq-cron-job"
        )
        # Build a synthetic cron expression from the constraints arq
        # stores on the job. arq cron is *not* a single cron string;
        # it's a tuple of (month, day, weekday, hour, minute, second).
        expr = " ".join(
            _arq_field(getattr(job, field, None))
            for field in ("minute", "hour", "day", "month", "weekday")
        )
        return Schedule(
            id=uuid4(),
            project_id=self._project_id,
            engine="arq",
            scheduler=self.name,
            name=name,
            task_name=name,
            kind=ScheduleKind.CRON,
            expression=expr or "*",
            timezone="UTC",
            is_enabled=True,
            external_id=name,
            created_at=now,
            updated_at=now,
        )


def _arq_field(value: Any) -> str:
    """Render an arq cron field constraint for a Schedule expression.

    arq accepts ``None`` (every value), ``int``, or
    ``set[int] / list[int]`` per field.
    """
    if value is None:
        return "*"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (set, list, tuple)):
        return ",".join(str(v) for v in sorted(value))
    return str(value)


__all__ = ["ArqCronAdapter"]
