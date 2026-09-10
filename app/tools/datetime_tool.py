from datetime import datetime
from zoneinfo import ZoneInfo


def get_datetime(
    timezone: str = "Asia/Kolkata",
) -> str:

    try:

        tz = ZoneInfo(timezone)

        now = datetime.now(tz)

        return (
            f"Date: {now.strftime('%Y-%m-%d')}\n"
            f"Time: {now.strftime('%H:%M:%S')}\n"
            f"Timezone: {timezone}\n"
            f"Day: {now.strftime('%A')}"
        )

    except Exception as exc:

        return f"Date/time error: {exc}"