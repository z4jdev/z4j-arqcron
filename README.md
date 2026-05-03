# z4j-arqcron

[![PyPI version](https://img.shields.io/pypi/v/z4j-arqcron.svg?v=1.4.0)](https://pypi.org/project/z4j-arqcron/)
[![Python](https://img.shields.io/pypi/pyversions/z4j-arqcron.svg?v=1.4.0)](https://pypi.org/project/z4j-arqcron/)
[![License](https://img.shields.io/pypi/l/z4j-arqcron.svg?v=1.4.0)](https://github.com/z4jdev/z4j-arqcron/blob/main/LICENSE)

The arq cron-jobs scheduler adapter for [z4j](https://z4j.com).

Surfaces every cron job your arq Settings class registers on the
dashboard's Schedules page, read, enable, disable, trigger.

## What it ships

| Capability | Notes |
|---|---|
| List schedules | every `cron_jobs` entry on your arq Settings |
| Read | by registered name |
| Enable / disable | via consumer-side gating |
| Trigger now | enqueues the task immediately, outside the schedule |
| Boot inventory | full snapshot at agent connect; existing cron jobs show up without editing |

arq cron jobs are defined declaratively on the WorkerSettings class, so
create / update / delete are intentionally out of scope, those need a
deploy round-trip. The dashboard hides buttons it can't honor.

## Install

```bash
pip install z4j-arq z4j-arqcron
```

```python
from arq import cron
from z4j_bare import install_agent
from z4j_arq import ArqEngineAdapter
from z4j_arqcron import ArqCronAdapter

class WorkerSettings:
    redis_settings = ...
    cron_jobs = [
        cron(cleanup, minute=set(range(0, 60, 5))),
    ]

install_agent(
    engines=[ArqEngineAdapter(settings=WorkerSettings)],
    schedulers=[ArqCronAdapter(settings=WorkerSettings)],
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
