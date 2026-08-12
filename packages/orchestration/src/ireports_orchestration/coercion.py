"""Coerce the shapes a model actually returns into the array that was requested (ADR-018).

**This module exists because the same fix was applied in one place and not the other, and the
gap cost a live run.** `specialist.py` carried this logic privately from the day the nested-envelope
bug was found. `synthesis.py` asks for two arrays from the same provider under the same structured
output setting, and parsed them by iterating whatever came back.

On 2026-08-12 the model returned synthesis's arrays as JSON *strings*. Iterating a string yields
characters, so a 2,895-character response produced 2,895 rejections reading
`synthesis/gap#2894: not an object — dropped`, zero findings, and no error. Both orchestrators
independently. The specialist path, on the same run, handled the identical shape correctly.

The lesson is in `LESSONS.md` and it is not "add a coercion to synthesis" — it is that a fix
living in a private helper is a fix that only applies where someone remembered it.
"""

from __future__ import annotations

import json
from typing import Any

MAX_UNWRAP_DEPTH = 3
"""How many layers of re-wrapping to peel before giving up. Three is generous; two were observed."""


def normalize_array(raw: Any, key: str) -> Any:
    """Return `raw` as a list if any documented coercion gets there, otherwise return it as-is.

    ADR-018 in practice. All of these came from the *same* schema and the same prompt:

    | Returned | Handling |
    |---|---|
    | `[...]` | The requested shape |
    | `"[...]"` — the array as a JSON string | Parse it |
    | `{...}` — one item where an array was asked for | Wrap it |
    | `{"<key>": [...]}` — the envelope repeated inside itself | **Unwrap it** |

    That last one is why this is a loop rather than two `if`s. An earlier version saw a dict and
    wrapped it, producing `[{"findings": [...]}]` — an "object missing every required field", which
    it duly rejected. So a response the model had answered correctly, only nested one layer too
    deep, was recorded as unparseable. **It was invisible for weeks** because the rejection said
    "missing/blank [title, observation, ...]" and stopped there.

    Unwrapping is only attempted when the dict's *sole* key is `key`. A dict that has that key
    alongside real item fields is ambiguous, and guessing there would risk discarding real content.

    **The caller must still check the result is a list.** This returns whatever it could not
    coerce, deliberately, so the caller can name what it actually got. Returning `[]` on failure
    would turn an unparseable response into a clean empty one — the silent under-analysis this
    whole architecture is built against.
    """
    for _ in range(MAX_UNWRAP_DEPTH):
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return None
        elif isinstance(raw, dict) and set(raw) == {key}:
            raw = raw[key]
        elif isinstance(raw, dict):
            return [raw]
        else:
            return raw
    return raw


MAX_REJECTIONS = 50
"""Cap on rejections recorded per stage, before the summary line.

Rejections are output, not error logging (`CLAUDE.md`) — but output has to stay readable to be
worth anything. The live run above produced 4,547 of them, which buried the two that mattered and
put 4,547 strings into the envelope's accounting payload. A cap plus an honest count is strictly
better than either an unbounded list or a silent truncation.

Fifty is a judgement. A genuine analysis produces a handful; anything past fifty is a malformed
response, and the fifty-first line tells you nothing the first fifty did not.
"""


def cap_rejections(rejected: list[str], limit: int = MAX_REJECTIONS) -> tuple[str, ...]:
    """Truncate a rejection list, **saying so**.

    The suppressed count is part of the record, not a detail dropped on the floor. A reader has to
    be able to tell "three findings were dropped" from "four thousand were, and you are seeing
    fifty" — those are different facts about the run, and conflating them is how a pathological
    response reads as a mild one.
    """
    if len(rejected) <= limit:
        return tuple(rejected)
    suppressed = len(rejected) - limit
    return (
        *rejected[:limit],
        f"... and {suppressed} more rejections of the same stage, suppressed. "
        f"{len(rejected)} in total — a count this high means a malformed response shape, "
        "not a record with that many problems.",
    )
