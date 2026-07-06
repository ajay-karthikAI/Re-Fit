"""The single gateway for all LLM calls (see CLAUDE.md).

Every call goes through the Anthropic SDK with structured outputs validated
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

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.schemas.llm import LLMUsage

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-8"
MAX_VALIDATION_RETRIES = 2
_PLACEHOLDER_KEYS = {"", "changeme"}


class LLMOutputInvalidError(Exception):
    """The model failed to produce schema-valid output after all retries."""


T = TypeVar("T", bound=BaseModel)


@lru_cache
def _client() -> AsyncAnthropic:
    key = get_settings().anthropic_api_key
    if key not in _PLACEHOLDER_KEYS:
        return AsyncAnthropic(api_key=key)
    # Fall back to the SDK's own credential resolution (env var, `ant auth login`
    # profile) so a placeholder in .env doesn't shadow real credentials.
    return AsyncAnthropic()


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

    `schema` should stay free of regex/format constraints — Anthropic's
    structured-output grammar compiler rejects schemas above a size threshold,
    and semantic constraints (date patterns, email/URL formats) on nested
    lists blow that budget. Do that stricter validation in `validate_extra`;
    a raised ValidationError there is treated the same as a schema-parse
    failure and feeds back into the retry loop. Its return value (if any)
    becomes this function's result — otherwise the raw parsed object is
    returned.

    Returns the (possibly revalidated) object and total token usage (summed
    across retries). Raises LLMOutputInvalidError when the retry budget is
    exhausted.
    """
    client = _client()
    model = model or DEFAULT_MODEL
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
    total = LLMUsage()
    last_error: Exception | None = None

    for attempt in range(1 + MAX_VALIDATION_RETRIES):
        response = None
        try:
            response = await client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=system,
                thinking={"type": "adaptive"},
                messages=messages,
                output_format=schema,
            )
            total = total + LLMUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
            parsed = response.parsed_output
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
                raw_text = next(
                    (block.text for block in response.content if block.type == "text"), ""
                )
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
