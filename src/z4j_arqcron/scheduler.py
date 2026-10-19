"""Native arq inventory, manual runs and durable dashboard schedule overrides."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from z4j_core.cron_fields import numeric_cron_field
from z4j_core.models import CommandResult, Schedule, ScheduleKind
from z4j_core.native_schedule_operations import direct_native_mutation
from z4j_core.protocols.scheduler import NativeScheduleOverrides
from z4j_core.schedule_external import (
    EXTERNAL_SCHEDULE_MUTATION_CAPABILITY,
    EXTERNAL_SCHEDULE_STABLE_SNAPSHOT_CAPABILITY,
    canonical_external_json,
)

from z4j_arqcron.capabilities import DEFAULT_CAPABILITIES

logger = logging.getLogger("z4j.adapter.arqcron.scheduler")

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
        cron_jobs: Iterable[Any] | None = None,
        project_id: UUID | None = None,
        worker: Any = None,
        control: NativeScheduleOverrides | None = None,
    ) -> None:
        self._cron_jobs: list[Any] = list(
            cron_jobs if cron_jobs is not None else worker.cron_jobs if worker is not None else []
        )
        self._project_id = project_id or uuid4()
        self._worker = worker
        self._control = control
        self._native_jobs: dict[str, tuple[str, Any]] = {}
        self._functions = dict(worker.functions) if worker is not None else {}
        if control is not None:
            if worker is None:
                raise ValueError("managed arq schedules require the actual Worker instance")
            if getattr(worker, "_z4j_cron_control", None) is not None:
                raise ValueError("this arq worker already has native schedule control")
            for schedule in control.resolve(self._baseline(), owner=self.name):
                self._validate(schedule)
            worker._z4j_cron_control = self
            self._original_run_cron = worker.run_cron
            worker.run_cron = self._run_cron

    def connect_signals(self, sink: Any) -> None:
        return

    def disconnect_signals(self) -> None:
        return

    async def list_schedules(self) -> list[Schedule]:
        baseline = self._baseline()
        return (
            await asyncio.to_thread(self._control.resolve, baseline, owner=self.name)
            if self._control
            else baseline
        )

    def _baseline(self) -> list[Schedule]:
        out: list[Schedule] = []
        for job in self._cron_jobs:
            try:
                out.append(self._to_schedule(job))
            except Exception:
                logger.exception(
                    "z4j arqcron: failed to map %r; skipping this authoritative snapshot",
                    getattr(job, "name", "?"),
                )
                raise
        return out

    async def get_schedule(self, schedule_id: str) -> Schedule | None:
        for s in await self.list_schedules():
            if schedule_id in {str(s.id), s.external_id, s.name}:
                return s
        return None

    async def create_schedule(self, spec: Schedule) -> Schedule:
        if self._control is not None:
            result = await direct_native_mutation(self, "create", None, spec)
            assert isinstance(result, Schedule)
            return result
        raise NotImplementedError(
            "arq cron jobs are statically configured; edit your "
            "WorkerSettings.cron_jobs and redeploy.",
        )

    async def update_schedule(
        self,
        schedule_id: str,
        spec: Schedule,
    ) -> Schedule:
        if self._control is not None:
            result = await direct_native_mutation(self, "update", schedule_id, spec)
            assert isinstance(result, Schedule)
            return result
        raise NotImplementedError(
            "arq cron jobs are statically configured; edit and redeploy.",
        )

    async def delete_schedule(self, schedule_id: str) -> CommandResult:
        if self._control is not None:
            result = await direct_native_mutation(self, "delete", schedule_id)
            assert isinstance(result, CommandResult)
            return result
        return CommandResult(
            status="failed",
            error="arq cron jobs are statically configured; remove from "
            "WorkerSettings.cron_jobs and redeploy.",
        )

    async def enable_schedule(self, schedule_id: str) -> CommandResult:
        if self._control is not None:
            result = await direct_native_mutation(self, "update", schedule_id, enabled=True)
            assert isinstance(result, CommandResult)
            return result
        return CommandResult(
            status="failed",
            error="arq cron jobs have no enable/disable toggle",
        )

    async def disable_schedule(self, schedule_id: str) -> CommandResult:
        if self._control is not None:
            result = await direct_native_mutation(self, "update", schedule_id, enabled=False)
            assert isinstance(result, CommandResult)
            return result
        return CommandResult(
            status="failed",
            error="arq cron jobs have no enable/disable toggle",
        )

    async def trigger_now(self, schedule_id: str) -> CommandResult:
        if self._worker is None:
            return CommandResult(
                status="failed", error="trigger_now requires the actual arq Worker"
            )

        async def send() -> CommandResult:
            schedule = await self.get_schedule(schedule_id)
            if schedule is None:
                raise ValueError("native schedule not found")
            self._validate(schedule)
            job = await self._worker.pool.enqueue_job(
                schedule.task_name,
                *schedule.args,
                _queue_name=self._worker.queue_name,
                **schedule.kwargs,
            )
            if job is None:
                raise ValueError("arq did not enqueue the manual run")
            return CommandResult(status="success", result={"task_id": job.job_id})

        try:
            return await asyncio.wait_for(self._on_worker(send), 10)
        except TimeoutError:
            return CommandResult(
                status="failed",
                error="arq enqueue timed out; inspect before retrying",
                result={"indeterminate": True},
            )
        except Exception as exc:
            return CommandResult(status="failed", error=str(exc))

    async def _on_worker(self, operation: Any) -> Any:
        loop = self._worker.loop
        if loop is asyncio.get_running_loop():
            return await operation()
        if loop.is_closed() or not loop.is_running():
            raise ValueError("arq worker event loop is unavailable")
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(operation(), loop))

    def _validate(self, schedule: Schedule) -> None:
        if schedule.task_name not in self._functions:
            raise ValueError("task must already be registered with this arq worker")
        if schedule.kind != ScheduleKind.CRON:
            raise ValueError("native arq schedules require cron")
        if schedule.queue not in {None, self._worker.queue_name}:
            raise ValueError("native arq schedules use the worker's queue")
        if any(k.startswith("_") for k in schedule.kwargs):
            raise ValueError("arq reserves underscore keyword arguments for enqueue options")
        self._timezone(schedule.timezone)
        self._constraints(schedule.expression)

    def _timezone(self, name: str) -> Any:
        if self._worker is not None and name == str(self._worker.timezone):
            return self._worker.timezone
        return ZoneInfo(name)

    @staticmethod
    def _constraints(expression: str) -> dict[str, Any]:
        fields = expression.split()
        if len(fields) == 5:
            fields = ["0", *fields]
        if len(fields) != 6:
            raise ValueError(
                "arq cron requires minute hour day month weekday, optionally prefixed by seconds"
            )
        return {
            key: _parse_field(value, low, high)
            for key, value, low, high in zip(
                ("second", "minute", "hour", "day", "month", "weekday"),
                fields,
                (0, 0, 0, 1, 1, 0),
                (59, 59, 23, 31, 12, 6),
                strict=True,
            )
        }

    async def _run_cron(self, now: datetime, delay: float, num_windows: int = 2) -> None:
        """Use arq's CronJob calculation and broker with committed definitions.

        Arguments are enqueued with the original registered function name, so a
        later edit cannot change the meaning of an already queued occurrence.
        """
        from copy import copy
        from datetime import timedelta

        from arq import cron
        from arq.utils import to_unix_ms

        try:
            schedules = await self.list_schedules()
            active = []
            due = []
            live_keys = {s.external_id for s in schedules if s.is_enabled}
            self._native_jobs = {
                key: value for key, value in self._native_jobs.items() if key in live_keys
            }
            for schedule in schedules:
                self._validate(schedule)
                key = schedule.external_id or ""
                if not schedule.is_enabled:
                    continue
                version = hashlib.sha256(
                    canonical_external_json(
                        {
                            "expression": schedule.expression,
                            "timezone": schedule.timezone,
                            "source_hash": schedule.source_hash,
                        }
                    )
                ).hexdigest()
                previous = self._native_jobs.get(key)
                if previous is not None and previous[0] == version:
                    job = previous[1]
                else:
                    original = next((j for j in self._cron_jobs if j.name == key), None)
                    if original is not None:
                        job = copy(original)
                        for field, value in self._constraints(schedule.expression).items():
                            setattr(job, field, value)
                        job.next_run = None
                    else:
                        job = cron(
                            self._functions[schedule.task_name].coroutine,
                            name=schedule.task_name,
                            microsecond=0,
                            **self._constraints(schedule.expression),
                        )
                    self._native_jobs[key] = (version, job)
                active.append(job)
                local_now = now.astimezone(self._timezone(schedule.timezone))
                if job.next_run is None:
                    if job.run_at_startup:
                        job.next_run = local_now
                    else:
                        job.calculate_next(local_now)
                        continue
                if job.next_run < now + timedelta(seconds=delay * num_windows):
                    occurrence = job.next_run
                    job_id = job.job_id or (
                        f"z4j:{key}:{to_unix_ms(occurrence)}" if job.unique else None
                    )
                    due.append((schedule, occurrence, job_id))
                    job.calculate_next(occurrence)
            self._worker.cron_jobs = active
        except Exception:
            logger.exception("native arq schedule read failed; periodic dispatch withheld")
            return
        # Errors publishing a due task follow arq's normal worker error path.
        await asyncio.gather(
            *(
                self._worker.pool.enqueue_job(
                    row.task_name,
                    *row.args,
                    _job_id=job_id,
                    _queue_name=self._worker.queue_name,
                    _defer_until=occurrence if occurrence > datetime.now(UTC) else None,
                    **row.kwargs,
                )
                for row, occurrence, job_id in due
            )
        )

    async def apply_external_mutation(
        self,
        *,
        operation: str,
        schedule_id: str | None,
        expected: dict[str, Any] | None,
        definition: dict[str, Any],
    ) -> Schedule | None:
        """Commit an override read by the arq worker's cron producer."""
        if self._control is None:
            raise ValueError("pass NativeScheduleControl and Worker to enable dashboard writes")
        return await asyncio.to_thread(
            self._control.mutate,
            owner=self.name,
            engine="arq",
            operation=operation,
            schedule_id=schedule_id,
            expected=expected,
            definition=definition,
            baseline=self._baseline(),
            validate=self._validate,
        )

    def capabilities(self) -> set[str]:
        caps = set(DEFAULT_CAPABILITIES) | {EXTERNAL_SCHEDULE_STABLE_SNAPSHOT_CAPABILITY}
        if self._worker is not None:
            caps.add("trigger_now")
        if self._control is not None:
            caps.update(
                {
                    EXTERNAL_SCHEDULE_MUTATION_CAPABILITY,
                    "create",
                    "update",
                    "delete",
                    "enable",
                    "disable",
                }
            )
        return caps

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
            for field in ("second", "minute", "hour", "day", "month", "weekday")
        )
        return Schedule(
            id=uuid5(NAMESPACE_URL, f"arq-cron:{name}"),
            project_id=self._project_id,
            engine="arq",
            scheduler=self.name,
            name=name,
            task_name=name,
            kind=ScheduleKind.CRON,
            expression=expr or "*",
            timezone=str(self._worker.timezone) if self._worker is not None else "UTC",
            is_enabled=True,
            external_id=name,
            source="arq-cron:code",
            source_hash=hashlib.sha256(
                canonical_external_json(
                    {
                        "expression": expr,
                        "microsecond": getattr(job, "microsecond", 0),
                        "run_at_startup": getattr(job, "run_at_startup", False),
                        "unique": getattr(job, "unique", True),
                        "job_id": getattr(job, "job_id", None),
                        "coroutine": f"{job.coroutine.__module__}.{job.coroutine.__qualname__}"
                        if getattr(job, "coroutine", None)
                        else name,
                    }
                )
            ).hexdigest(),
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
    if isinstance(value, str):
        weekdays = {"mon": 0, "tues": 1, "wed": 2, "thurs": 3, "fri": 4, "sat": 5, "sun": 6}
        return str(weekdays.get(value.lower(), value))
    return str(value)


def _parse_field(value: str, low: int, high: int) -> int | set[int] | None:
    if value == "*":
        return None
    selected = numeric_cron_field(value, low, high)
    return selected[0] if len(selected) == 1 else set(selected)


__all__ = ["ArqCronAdapter"]
