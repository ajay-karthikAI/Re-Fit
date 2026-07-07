"""Shared guard so an eval can never silently run on a placeholder LLM key.

Every eval entry point calls ``guard_llm_or_exit`` at the top. With a real key
it is a no-op. With a placeholder-shaped key it prints a loud, red-flagged
banner and either exits nonzero (default) or, only if ``--allow-heuristic`` was
passed, continues in heuristic mode — which the caller must then reflect in the
report header, not just the logs.
"""

from __future__ import annotations

import sys

from app.config import get_settings
from app.services.llm import is_placeholder_key

_BANNER = "\033[1;41;97m"  # bold white on red
_RESET = "\033[0m"

HEURISTIC_REPORT_HEADER = (
    "> ⚠️ **HEURISTIC MODE** — generated with NO real LLM key. JD requirements "
    'come from the deterministic keyword approximation (`source="heuristic"`), '
    "NOT a real extraction. Results are indicative only and MUST NOT be used as a "
    "real eval of tailoring/matching quality."
)


def guard_llm_or_exit(allow_heuristic: bool, script_name: str) -> bool:
    """Return True if running in heuristic mode, False for the real LLM path.

    Exits nonzero when the key is placeholder-shaped and ``allow_heuristic`` is
    False.
    """
    key = get_settings().openai_api_key
    if not is_placeholder_key(key):
        return False  # real key: real path, nothing to warn about

    banner_lines = [
        "",
        f"{_BANNER}  ══════════════════════════════════════════════════════════════  {_RESET}",
        f"{_BANNER}  NO REAL LLM KEY CONFIGURED (OPENAI_API_KEY is empty/placeholder)  {_RESET}",
        f"{_BANNER}  {script_name}: refusing to run a real eval without a real key.    {_RESET}",
        f"{_BANNER}  ══════════════════════════════════════════════════════════════  {_RESET}",
        "",
    ]
    print("\n".join(banner_lines), file=sys.stderr)

    if not allow_heuristic:
        print(
            "Pass --allow-heuristic to run in clearly-labelled heuristic mode "
            "(approximation only), or configure a real OPENAI_API_KEY.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    print(
        f"{_BANNER}  --allow-heuristic set: continuing in HEURISTIC MODE (approximate).  {_RESET}\n",
        file=sys.stderr,
    )
    return True
