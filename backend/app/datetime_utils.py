from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return a timezone-naive UTC value suitable for MySQL DATETIME columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(value: datetime | None) -> str | None:
    """Serialize DATETIME values explicitly as UTC instead of ambiguous local time."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")
