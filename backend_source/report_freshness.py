
from datetime import datetime, timezone, timedelta

def classify_report_freshness(value, now=None):
    try:
        timestamp = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        raise ValueError("Invalid report timestamp")

    if timestamp.tzinfo is None:
        raise ValueError("Timezone required")

    now = now or datetime.now(timezone.utc)

    if timestamp > now + timedelta(minutes=5):
        raise ValueError("Future-dated report rejected")

    if now - timestamp > timedelta(hours=3):
        return "STALE"

    return "RECENT_TIMESTAMP_ONLY"
