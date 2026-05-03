"""Google Calendar API ラッパー。

指定日（または期間）の予定一覧を取得する。
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from .config import Config, Member
from .google_auth import get_credentials
from .models import CalendarEvent


def _build_service(config: Config):
    creds = get_credentials(config.google_credentials_path, config.google_token_path)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _parse_event(item: dict, tz: ZoneInfo) -> CalendarEvent | None:
    start_raw = item.get("start", {})
    end_raw = item.get("end", {})
    start_str = start_raw.get("dateTime") or start_raw.get("date")
    end_str = end_raw.get("dateTime") or end_raw.get("date")
    if not start_str or not end_str:
        return None

    def _to_dt(s: str) -> datetime:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(tz)
        d = datetime.strptime(s, "%Y-%m-%d").date()
        return datetime.combine(d, time.min, tzinfo=tz)

    return CalendarEvent(
        id=item.get("id", ""),
        title=item.get("summary", ""),
        start=_to_dt(start_str),
        end=_to_dt(end_str),
        attendees=[a.get("email", "") for a in item.get("attendees", []) if a.get("email")],
    )


def fetch_events(
    config: Config,
    member: Member,
    start_date: date,
    end_date: date,
) -> list[CalendarEvent]:
    if not member.calendar_id:
        return []
    tz = ZoneInfo(config.timezone)
    service = _build_service(config)
    time_min = datetime.combine(start_date, time.min, tzinfo=tz).isoformat()
    time_max = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz).isoformat()

    events_out: list[CalendarEvent] = []
    page_token = None
    while True:
        resp = service.events().list(
            calendarId=member.calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token,
        ).execute()
        for item in resp.get("items", []):
            ev = _parse_event(item, tz)
            if ev:
                events_out.append(ev)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return events_out
