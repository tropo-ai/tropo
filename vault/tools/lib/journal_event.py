"""Read names from run journals, including historical publication mirrors.

This helper is for run journals only. An entity inventory's type field is
not an event name. Each caller still owns vocabulary and authorization.
"""


def run_journal_event_type(row) -> str:
    """Use the legacy alias only for an absent, null, or empty canonical key."""
    if not isinstance(row, dict):
        return ""
    value = row.get("event")
    if value is None or value == "":
        value = row.get("type")
    return value if isinstance(value, str) else ""
