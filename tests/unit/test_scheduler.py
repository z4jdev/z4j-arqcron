"""ArqCronAdapter tests."""

from __future__ import annotations

import pytest

pytest.importorskip("arq")

from arq import cron  # noqa: E402

from z4j_arqcron import ArqCronAdapter  # noqa: E402


async def cleanup_handler(ctx):  # pragma: no cover
    return "ok"


async def nightly(ctx):  # pragma: no cover
    return "ok"


@pytest.fixture
def adapter():
    cron_jobs = [
        cron(cleanup_handler, minute={5, 10, 15}, name="cleanup"),
        cron(nightly, hour=3, minute=0, name="nightly_backup"),
    ]
    return ArqCronAdapter(cron_jobs=cron_jobs)


@pytest.mark.asyncio
async def test_lists_cron_jobs(adapter):
    rows = await adapter.list_schedules()
    names = {r.name for r in rows}
    assert "cleanup" in names
    assert "nightly_backup" in names
    assert all(r.engine == "arq" for r in rows)
    assert all(r.scheduler == "arq-cron" for r in rows)


@pytest.mark.asyncio
async def test_get_by_name(adapter):
    found = await adapter.get_schedule("nightly_backup")
    assert found is not None
    assert found.name == "nightly_backup"


@pytest.mark.asyncio
async def test_unknown_name_returns_none(adapter):
    assert await adapter.get_schedule("does-not-exist") is None


@pytest.mark.asyncio
async def test_mutations_clearly_unsupported(adapter):
    res = await adapter.delete_schedule("cleanup")
    assert res.status == "failed"
    res = await adapter.enable_schedule("cleanup")
    assert res.status == "failed"
    res = await adapter.trigger_now("cleanup")
    assert res.status == "failed"


@pytest.mark.asyncio
async def test_create_raises_not_implemented(adapter):
    with pytest.raises(NotImplementedError):
        await adapter.create_schedule(spec=None)  # type: ignore[arg-type]
