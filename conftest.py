"""The pytest session's entry point — and the only place in this repo that reads `.env`.

ADR-016. Library code is a pure consumer of `os.environ`: `GatewayConfig.from_env()` and
`ireports_spike_harness.gateway.DEFAULT_DSN` read variables and never a file. That is deliberate.
A library that loads `.env` from the current working directory acquires a hidden dependency on
where the process happened to be started, and in Lambda there is no `.env` at all — so local and
deployed behaviour would diverge for reasons that have nothing to do with configuration.

So the file is loaded at **entry points**, explicitly. There are two today:

1. This module — the pytest session.
2. `uv run --env-file .env <command>` — ad hoc commands outside pytest.

When `apps/api` lands it becomes the third, and it calls a loader in its own `main`, not in a
package anything else imports.

`override=False` is load-bearing: a variable already present in the real environment wins over
the file. CI, a container, and a deployed function therefore cannot be silently overridden by a
`.env` that happens to be on disk.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent

load_dotenv(REPO_ROOT / ".env", override=False)
