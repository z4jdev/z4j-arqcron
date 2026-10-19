# z4j-arqcron

The native arq cron adapter for [z4j](https://z4j.com), with dashboard management
of cron jobs. Dashboard management needs the z4j server, `z4j-core`, `z4j-bare`
and this adapter from the same release, plus the producer setup below.

## Compatibility

arq 0.26+; Python 3.11+.

## Installation and producer setup

Install `z4j-arqcron` and `z4j-bare` from the same release wave, plus the native
scheduler and broker/store dependencies used by your application. The example
assumes your task code, writable application-state directory and agent credentials
already exist. Use the project UUID from agent registration.

```python
import asyncio
import os
from datetime import UTC
from arq import cron
from arq.worker import Worker
from myapp.jobs import cleanup
from z4j_arqcron import ArqCronAdapter
from z4j_bare import NativeScheduleControl, install_agent

async def main():
    worker = Worker(functions=[cleanup], cron_jobs=[cron(cleanup, hour=3)], timezone=UTC)
    adapter = ArqCronAdapter(
        worker=worker,
        control=NativeScheduleControl("/var/lib/myapp/arq-schedules.sqlite3"),
    )
    agent = install_agent(
        engines=[], schedulers=[adapter],
        brain_url=os.environ["Z4J_BRAIN_URL"], token=os.environ["Z4J_TOKEN"],
        hmac_secret=os.environ["Z4J_HMAC_SECRET"], project_id=os.environ["Z4J_PROJECT_ID"],
    )
    try:
        await worker.main()
    finally:
        agent.stop()
        await worker.close()

asyncio.run(main())
```

Pass the actual running `Worker`, not just `WorkerSettings.cron_jobs`, to enable
native control. The iterable-only constructor remains an inventory adapter.
A worker-bound adapter without `control` also permits manual runs.

## Dashboard controls

The connected producer supports inventory, create, edit, pause, resume, delete
and **Run now**. A write is complete only after z4j accepts a snapshot confirming
the native source. The dashboard uses the current connection's advertised
capabilities; an unavailable producer cannot accept new edits. Repeating an
operation ID does not submit it twice. A timeout or uncertain outcome requires
inspection before submitting a new request.

A pause prevents future scheduling. Work already queued or running can finish.
Run now submits an additional execution without resuming a paused schedule.
Native scheduling keeps the upstream scheduler's timing and delivery semantics;
it does not acquire z4j-scheduler's catch-up, overlap or exactly-once guarantees.
Queue task history requires the corresponding engine adapter in the workers.

## Code definitions and durable overrides

`NativeScheduleControl` stores dashboard changes in a private SQLite file in
the producer's application state directory. Keep that file on a durable local
volume, back it up with the application, and reuse the same path after restart.
Use a separate file for each application and scheduler owner. Do not put it on
an ephemeral container filesystem or a network filesystem.

Code supplies the initial definitions. Each saved change overrides the fields
it submits: pause and resume submit only the enabled flag, while the dashboard
edit form submits every editable field (task, schedule type, expression,
timezone, queue, arguments and enabled flag), so later code changes to those
fields stay hidden. Removing a code definition removes its projection;
reintroducing the same source identity restores any saved override. Deletion is
a durable tombstone, so restarting the application does not recreate it.
Dashboard-created schedules survive with the same file. No Python files are
rewritten. New schedules can invoke only tasks already registered in the host
application; deploying new task code remains an application operation.

The producer reads committed controls locally and keeps scheduling during a
z4j server outage. If that local state cannot be read or validated, periodic
dispatch is withheld and the error is logged. Normal task processing continues.
Install control before starting periodic dispatch. Keep one managed periodic
producer per application; its dashboard overrides live in that worker's local
control file. There is currently no separate dashboard action to remove an
override and restore the code default.

## Supported definitions and limits

- Five cron fields mean minute, hour, day, month, weekday. Six fields prefix seconds. Numeric weekdays use Monday=0 through Sunday=6.
- Native named weekdays and worker timezone offsets are preserved. New timezone choices use IANA names.
- Existing cron microseconds, startup behavior, uniqueness and job identity are preserved when editing a definition.
- The worker's registered functions and cron functions are the allowed tasks. Its configured queue handles the executions.
- Keyword names beginning with `_` are reserved by arq enqueue options and are rejected for dashboard task arguments.

## Links

- [Documentation](https://docs.z4j.com/schedulers/arq-cron/)
- [Changelog](https://github.com/z4jdev/z4j-arqcron/blob/main/CHANGELOG.md)
- [Security policy](https://github.com/z4jdev/z4j-arqcron/blob/main/SECURITY.md); report vulnerabilities to security@z4j.com
- [Apache-2.0 license](https://github.com/z4jdev/z4j-arqcron/blob/main/LICENSE)
