"""Schema for a single job posting as returned by an external source client.

A ``RawPosting`` is the normalized shape every ``SourceClient`` maps to,
regardless of which upstream API it came from. It is deliberately *raw*: the
description is kept as HTML in ``raw_description_html`` and cleaned to text
lazily via ``description_text`` (see ``app/services/sources/base.py``), so the
mapping layer stays a pure field re-shuffle with no lossy transforms.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

SourceName = Literal["greenhouse", "lever", "rss"]


class RawPosting(BaseModel):
    """One job posting from an external board, source-agnostic."""

    model_config = ConfigDict(extra="forbid")

    external_id: str
    """The posting's id on the source, stringified (e.g. Greenhouse int, Lever uuid)."""
    title: str
    location: str | None
    department: str | None
    url: str
    """Public, human-facing apply/listing URL for this posting."""
    raw_description_html: str
    """Description as HTML (Greenhouse ``content``, Lever ``description``) or plain
    text (Lever ``descriptionPlain``). Clean it with ``description_text``."""
    posted_at: datetime | None
    source: SourceName

    @property
    def description_text(self) -> str:
        """Description as clean, structure-preserving plain text.

        Runs the shared ``html_to_text`` helper, which is a no-op-ish pass for
        already-plain inputs, so callers never branch on the source.
        """
        from app.services.sources.base import html_to_text

        return html_to_text(self.raw_description_html)
