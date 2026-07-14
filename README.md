# z4j-arqcron

[![PyPI version](https://img.shields.io/pypi/v/z4j-arqcron.svg?v=1.7.0)](https://pypi.org/project/z4j-arqcron/)
[![Python](https://img.shields.io/pypi/pyversions/z4j-arqcron.svg?v=1.7.0)](https://pypi.org/project/z4j-arqcron/)
[![License](https://img.shields.io/pypi/l/z4j-arqcron.svg?v=1.7.0)](https://github.com/z4jdev/z4j-arqcron/blob/main/LICENSE)

The arq cron-jobs scheduler adapter for [z4j](https://z4j.com).

Surfaces every cron job your arq `WorkerSettings` class registers on the
dashboard's Schedules page, read-only (list and read).

## Compatibility

- arq 0.26+ and <1
- Python 3.11+

Full per-adapter matrix at <https://z4j.dev/reference/compatibility/>.

## What it ships

| Capability | Notes |
|---|---|
| List schedules | every `cron_jobs` entry on your arq `WorkerSettings` |
| Read | by registered name |
| Boot inventory | full snapshot at agent connect; existing cron jobs show up without editing |

This adapter is read-only by design. arq cron jobs are defined
declaratively on the `WorkerSettings` class, and arq exposes no runtime
enable/disable toggle or trigger-now primitive, so create / update /
delete / enable / disable / trigger now are all out of scope, those need
a deploy round-trip (or, for a one-off run, enqueue the underlying
coroutine via `ArqRedis.enqueue_job()`). The dashboard hides buttons it
can't honor.

## Install

```bash
pip install z4j-arq z4j-arqcron
```

```python
from arq import cron
from z4j_bare import install_agent
from z4j_arq import ArqEngineAdapter
from z4j_arqcron import ArqCronAdapter

async def cleanup(ctx):
    ...

class WorkerSettings:
    redis_settings = ...  # arq.connections.RedisSettings
    functions = [cleanup]
    cron_jobs = [
        cron(cleanup, minute=set(range(0, 60, 5))),
    ]

install_agent(
    engines=[
        ArqEngineAdapter(
            redis_settings=WorkerSettings.redis_settings,
            function_names=["cleanup"],
        ),
    ],
    schedulers=[ArqCronAdapter(cron_jobs=WorkerSettings.cron_jobs)],
    brain_url="https://brain.example.com",
    token="z4j_agent_...",
    project_id="my-project",
)
```

## Pairs with

- [`z4j-arq`](https://github.com/z4jdev/z4j-arq), engine adapter

## Reliability

- No exception from the adapter ever propagates back into arq's worker
  loop or your job code.
- The cron-jobs registry is read-only at runtime; the adapter only
  observes, it does not rewrite WorkerSettings.

## Documentation

Full docs at [z4j.dev/schedulers/arq-cron/](https://z4j.dev/schedulers/arq-cron/).

## License

Apache-2.0, see [LICENSE](LICENSE).

## Links

- Homepage: https://z4j.com
- Documentation: https://z4j.dev
- PyPI: https://pypi.org/project/z4j-arqcron/
- Issues: https://github.com/z4jdev/z4j-arqcron/issues
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Security: security@z4j.com (see [SECURITY.md](SECURITY.md))
