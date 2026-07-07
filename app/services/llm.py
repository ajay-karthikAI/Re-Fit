"""The single gateway for all LLM calls (see CLAUDE.md).

Every call goes through the OpenAI SDK with structured outputs validated
against Pydantic schemas from app/schemas/. No raw json.loads on model text
happens anywhere else in the codebase.

Retry policy per CLAUDE.md: max 2 retries on validation failure, re-prompting
with the validation error included; after that raise LLMOutputInvalidError —
never return partially-valid data.
"""

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.schemas.llm import LLMUsage

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.5"
MAX_VALIDATION_RETRIES = 2


class LLMOutputInvalidError(Exception):
    """The model failed to produce schema-valid output after all retries."""


class MissingLLMCredentialsError(Exception):
    """No usable LLM API key is configured (empty or a placeholder like the
    ``changeme`` shipped in .env.example). Raised instead of silently degrading
    to an approximation — a heuristic fallback must be opted into explicitly."""


T = TypeVar("T", bound=BaseModel)


def is_placeholder_key(key: str | None) -> bool:
    """True when ``key`` is unset or placeholder-shaped (empty, or starts with
    ``change`` as in ``changeme``). The single definition of "no real key" used
    both by the client and by any opt-in fallback gate."""
    stripped = (key or "").strip().lower()
    return not stripped or stripped.startswith("change")


@lru_cache
def _client() -> AsyncOpenAI:
    key = get_settings().openai_api_key
    if not is_placeholder_key(key):
        return AsyncOpenAI(api_key=key)
    # Fall back to the SDK's own credential resolution so a placeholder in .env
    # doesn't shadow real credentials from the process environment.
    return AsyncOpenAI()


async def generate_structured(
    schema: type[T],
    *,
    system: str,
    user_content: str,
    model: str | None = None,
    max_tokens: int = 16000,
    validate_extra: Callable[[T], Any] | None = None,
) -> tuple[Any, LLMUsage]:
    """One structured-output call, validated against `schema`.

    `schema` should stay friendly to provider-side structured outputs. Put
    stricter semantic constraints in `validate_extra`; a raised
    ValidationError there is treated the same as a schema-parse failure and
    feeds back into the retry loop. Its return value (if any) becomes this
    function's result — otherwise the raw parsed object is returned.

    Returns the (possibly revalidated) object and total token usage (summed
    across retries). Raises LLMOutputInvalidError when the retry budget is
    exhausted.
    """
    client = _client()
    model = model or DEFAULT_MODEL
    messages: list[dict[str, str]] = [{"role": "user", "content": user_content}]
    total = LLMUsage()
    last_error: Exception | None = None

    for attempt in range(1 + MAX_VALIDATION_RETRIES):
        response = None
        try:
            response = await client.responses.parse(
                model=model,
                instructions=system,
                input=messages,
                max_output_tokens=max_tokens,
                text_format=schema,
            )
            total = total + LLMUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ValueError("model returned no parseable structured output")
            result = validate_extra(parsed) if validate_extra is not None else parsed
            logger.info(
                "llm ok schema=%s model=%s attempt=%d input_tokens=%d output_tokens=%d",
                schema.__name__,
                model,
                attempt,
                total.input_tokens,
                total.output_tokens,
            )
            return result, total
        except (ValidationError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "llm validation failure schema=%s model=%s attempt=%d error=%s",
                schema.__name__,
                model,
                attempt,
                exc,
            )
            if response is not None:
                raw_text = response.output_text
                if raw_text:
                    messages.append({"role": "assistant", "content": raw_text})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous response failed schema validation with this "
                        f"error:\n\n{exc}\n\n"
                        "Return a corrected response that strictly matches the schema. "
                        "Do not invent any information that is not in the source material."
                    ),
                }
            )

    raise LLMOutputInvalidError(
        f"model output for {schema.__name__} still invalid after "
        f"{MAX_VALIDATION_RETRIES} retries: {last_error}"
    )
