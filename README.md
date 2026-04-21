# z4j-arqcron

[![PyPI version](https://img.shields.io/pypi/v/z4j-arqcron.svg)](https://pypi.org/project/z4j-arqcron/)
[![Python](https://img.shields.io/pypi/pyversions/z4j-arqcron.svg)](https://pypi.org/project/z4j-arqcron/)
[![License](https://img.shields.io/pypi/l/z4j-arqcron.svg)](https://github.com/z4jdev/z4j-arqcron/blob/main/LICENSE)


Read-only scheduler adapter for arq's `cron_jobs`.

```python
from arq import cron
from z4j_arq import ArqEngineAdapter
from z4j_arqcron import ArqCronAdapter

cron_jobs = [
    cron(send_summary, hour=3, minute=0, name="daily_summary"),
]

# In your z4j-bare bootstrap:
from z4j_bare import install_agent
install_agent(
    engines=[ArqEngineAdapter(...)],
    schedulers=[ArqCronAdapter(cron_jobs=cron_jobs)],
)
```

arq cron jobs are registered statically in `WorkerSettings.cron_jobs`,
so this adapter is read-only by design (same constraints as
`z4j-hueyperiodic`).

Apache 2.0.

## License

Apache 2.0 - see [LICENSE](LICENSE). This package is deliberately permissively licensed so that proprietary Django / Flask / FastAPI applications can import it without any license concerns.

## Links

- Homepage: <https://z4j.com>
- Documentation: <https://z4j.dev>
- Source: <https://github.com/z4jdev/z4j-arqcron>
- Issues: <https://github.com/z4jdev/z4j-arqcron/issues>
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Security: `security@z4j.com` (see [SECURITY.md](SECURITY.md))
