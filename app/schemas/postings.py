from pydantic import BaseModel, ConfigDict


class IngestResult(BaseModel):
    """Outcome of upserting one board's fetch into the postings table."""

    model_config = ConfigDict(extra="forbid")

    created: int = 0
    """Postings seen for the first time on this board."""
    updated: int = 0
    """Existing postings whose content changed (or that were reactivated) —
    these should re-trigger match scoring."""
    unchanged: int = 0
    """Existing postings re-seen with an identical content hash."""
    deactivated: int = 0
    """Postings previously active on this board but absent from this fetch."""
