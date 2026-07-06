"""Domain errors raised by services; translated to HTTP responses in app/main.py."""


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class UnsupportedFormatError(Exception):
    """Uploaded file is not a format we can extract text from (HTTP 415)."""


class FileTooLargeError(Exception):
    """Uploaded file exceeds the size cap (HTTP 413)."""


class ProseVerificationError(Exception):
    """Generated prose failed deterministic claim verification (HTTP 422)."""
