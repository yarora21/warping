import os
from datetime import date, datetime
from zoneinfo import ZoneInfo


def today() -> date:
    fixed = os.environ.get("APP_TODAY")
    return date.fromisoformat(fixed) if fixed else datetime.now(ZoneInfo(timezone())).date()


def timezone() -> str:
    return os.environ.get("COMPANY_TIMEZONE", "America/New_York")
