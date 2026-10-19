"""arq producer reads durable controls while preserving queued task inputs."""

from datetime import UTC, datetime, timedelta

import pytest
from arq import cron
from arq.worker import Worker, func
from z4j_arqcron import ArqCronAdapter
from z4j_bare import NativeScheduleControl
from z4j_core.schedule_external import normalize_external_schedule


class Pool:
    def __init__(self):
        self.sent = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.sent.append((name, args, kwargs))
        return type("Job", (), {"job_id": "manual"})()


async def record(ctx, value=42):
    return value


def make_app(path):
    pool = Pool()
    worker = Worker(
        functions=[func(record, name="record")],
        cron_jobs=[cron(record, name="code-record", second={0, 30}, microsecond=123456)],
        redis_pool=pool,
        handle_signals=False,
        timezone=UTC,
    )
    adapter = ArqCronAdapter(worker=worker, control=NativeScheduleControl(path))
    return worker, pool, adapter


async def change(adapter, row, definition, operation="update"):
    return await adapter.apply_external_mutation(
        operation=operation,
        schedule_id=row.external_id,
        expected=normalize_external_schedule(row.model_dump(mode="json"), owner=adapter.name),
        definition=definition,
    )


@pytest.mark.asyncio
async def test_native_cron_creation_edit_pause_restart_and_arguments(tmp_path):
    path = tmp_path / "schedules.sqlite3"
    worker, pool, adapter = make_app(path)
    now = datetime(2026, 10, 15, 12, 0, 1, tzinfo=UTC)
    created = await adapter.apply_external_mutation(
        operation="create",
        schedule_id=None,
        expected=None,
        definition={
            "name": "every-second",
            "task_name": "record",
            "kind": "cron",
            "expression": "* * * * * *",
            "args": [7],
        },
    )
    await worker.run_cron(now, 0.1)
    await worker.run_cron(now + timedelta(seconds=1), 0.1)
    assert pool.sent[-1][0:2] == ("record", (7,))
    edited = await change(adapter, created, {"args": [99]})
    assert pool.sent[-1][1] == (7,)  # an edit cannot rewrite an already queued occurrence
    paused = await change(adapter, edited, {"is_enabled": False})
    restarted_worker, restarted_pool, restarted = make_app(path)
    restored = await restarted.get_schedule(paused.external_id)
    assert restored is not None and not restored.is_enabled
    await restarted_worker.run_cron(now, 0.1)
    await restarted_worker.run_cron(now + timedelta(seconds=1), 0.1)
    assert restarted_pool.sent == []
    assert (await restarted.trigger_now(paused.external_id)).status == "success"
    assert restarted_pool.sent[-1][0:2] == ("record", (99,))
    await change(restarted, restored, {}, "delete")
    assert await restarted.get_schedule(restored.external_id) is None


@pytest.mark.asyncio
async def test_code_cron_precision_is_preserved_and_stale_edits_refused(tmp_path):
    worker, _, adapter = make_app(tmp_path / "schedules.sqlite3")
    row = (await adapter.list_schedules())[0]
    assert row.expression.startswith("0,30 ")
    now = datetime(2026, 10, 15, 12, 0, 1, tzinfo=UTC)
    await worker.run_cron(now, 0.1)
    assert worker.cron_jobs[0].next_run.microsecond == 123456
    await change(adapter, row, {"is_enabled": False})
    with pytest.raises(ValueError, match="changed"):
        await change(adapter, row, {"expression": "* * * * * *"})


@pytest.mark.asyncio
async def test_native_named_weekday_and_fixed_offset_are_preserved(tmp_path):
    from datetime import timezone

    worker = Worker(
        functions=[func(record, name="record")],
        cron_jobs=[cron(record, name="monday", weekday="mon", hour=3)],
        redis_pool=Pool(),
        handle_signals=False,
        timezone=timezone(timedelta(hours=2)),
    )
    adapter = ArqCronAdapter(
        worker=worker, control=NativeScheduleControl(tmp_path / "cron.sqlite3")
    )
    row = (await adapter.list_schedules())[0]
    assert row.expression.endswith(" 0")
    edited = await change(adapter, row, {"args": [99]})
    assert edited.timezone == "UTC+02:00"
    await worker.run_cron(datetime(2026, 10, 15, 12, 0, tzinfo=UTC), 0.1)
    assert worker.cron_jobs[0].next_run.utcoffset() == timedelta(hours=2)
