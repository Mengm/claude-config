#!/usr/bin/env python3
"""Manage Feishu calendar events (Calendar V4 API)."""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

from feishu_auth import api_get, api_post, api_delete


def _user_id_type() -> str:
    uid = os.getenv("TASKPOOL_USER_ID", "")
    if uid.startswith("ou_"):
        return "open_id"
    if uid.startswith("on_"):
        return "union_id"
    return "open_id"


def _parse_time(s: str, all_day: bool = False) -> dict:
    """Parse ISO time string to Feishu time_info.

    Accepts: "2026-02-15" (date) or "2026-02-15T14:00" (datetime).
    Returns: {"date": "YYYY-MM-DD"} for all-day, or {"timestamp": "seconds", "timezone": tz}.
    """
    s = s.strip()
    tz = os.getenv("SCHEDULER_TIMEZONE", "Asia/Shanghai")
    if all_day or "T" not in s:
        dt = datetime.fromisoformat(s)
        return {"date": dt.strftime("%Y-%m-%d")}
    else:
        dt = datetime.fromisoformat(s)
        return {"timestamp": str(int(dt.timestamp())), "timezone": tz}


def get_primary_calendar_id(as_user: bool = False) -> str:
    """Get the primary calendar ID (bot or user depending on as_user)."""
    resp = api_post("/calendar/v4/calendars/primary", as_user=as_user)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    calendars = resp.get("data", {}).get("calendars", [])
    if not calendars:
        print("ERROR: no primary calendar found", file=sys.stderr)
        sys.exit(1)
    return calendars[0].get("calendar", {}).get("calendar_id", "")


def list_calendars() -> list:
    """List all calendars accessible to the current identity."""
    resp = api_get("/calendar/v4/calendars")
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("calendar_list", [])


def create_event(calendar_id: str, summary: str, start: str, end: str | None = None,
                 description: str | None = None, all_day: bool = False,
                 location: str | None = None, reminders: list | None = None,
                 recurrence: str | None = None,
                 as_user: bool = False) -> dict:
    """Create a calendar event."""
    start_time = _parse_time(start, all_day)

    if end:
        end_time = _parse_time(end, all_day)
    elif all_day:
        # All-day: Feishu uses exclusive end date, so +1 day
        dt = datetime.fromisoformat(start.strip())
        dt_end = dt + timedelta(days=1)
        end_time = {"date": dt_end.strftime("%Y-%m-%d")}
    else:
        # Non-all-day: default to start + 1 hour
        dt = datetime.fromisoformat(start.strip())
        dt_end = dt + timedelta(hours=1)
        tz = os.getenv("SCHEDULER_TIMEZONE", "Asia/Shanghai")
        end_time = {"timestamp": str(int(dt_end.timestamp())), "timezone": tz}

    body = {
        "summary": summary,
        "start_time": start_time,
        "end_time": end_time,
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = {"name": location}
    if reminders:
        body["reminders"] = reminders
    if recurrence:
        body["recurrence"] = recurrence

    params = {"user_id_type": _user_id_type()}
    resp = api_post(f"/calendar/v4/calendars/{calendar_id}/events", body=body, params=params, as_user=as_user)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {}).get("event", {})


def add_attendees(calendar_id: str, event_id: str, attendee_ids: list[str],
                  notify: bool = True, as_user: bool = False) -> dict:
    """Add attendees to an event (separate API call after create)."""
    attendees = [{"type": "user", "user_id": uid} for uid in attendee_ids]
    params = {"user_id_type": _user_id_type()}
    body = {"attendees": attendees, "need_notification": notify}
    resp = api_post(
        f"/calendar/v4/calendars/{calendar_id}/events/{event_id}/attendees",
        body=body, params=params, as_user=as_user,
    )
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def delete_event(calendar_id: str, event_id: str) -> dict:
    """Delete a calendar event."""
    resp = api_delete(f"/calendar/v4/calendars/{calendar_id}/events/{event_id}")
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def list_events(calendar_id: str, start_time: str | None = None,
                end_time: str | None = None, page_size: int = 50,
                page_token: str | None = None) -> dict:
    """List events in a calendar within a time range."""
    params = {"page_size": page_size}
    if start_time:
        dt = datetime.fromisoformat(start_time.strip())
        params["start_time"] = str(int(dt.timestamp()))
    if end_time:
        dt = datetime.fromisoformat(end_time.strip())
        params["end_time"] = str(int(dt.timestamp()))
    if page_token:
        params["page_token"] = page_token
    resp = api_get(f"/calendar/v4/calendars/{calendar_id}/events", params=params)
    if resp.get("code") != 0:
        print(f"ERROR: {resp.get('msg', 'unknown error')} (code={resp.get('code')})", file=sys.stderr)
        sys.exit(1)
    return resp.get("data", {})


def _brief_events(data: dict) -> dict:
    """Compact list-events output: keep only key fields per event."""
    events = data.get("items", [])
    brief = []
    for ev in events:
        brief.append({
            "event_id": ev.get("event_id"),
            "summary": ev.get("summary", ""),
            "start_time": ev.get("start_time"),
            "end_time": ev.get("end_time"),
            "status": ev.get("status"),
        })
    out = {"items": brief}
    if data.get("has_more"):
        out["has_more"] = True
        out["page_token"] = data.get("page_token")
    return out


def main():
    parser = argparse.ArgumentParser(description="Manage Feishu calendar events")
    parser.add_argument("--action", required=True,
                        choices=["create", "delete", "list-calendars",
                                 "list-events", "add-attendees", "get-primary"])
    parser.add_argument("--calendar-id", help="Calendar ID (omit to use bot primary calendar)")
    parser.add_argument("--event-id", help="Event ID")
    parser.add_argument("--summary", help="Event title")
    parser.add_argument("--description", help="Event description")
    parser.add_argument("--start", help="Start time (ISO: 2026-02-15 or 2026-02-15T14:00)")
    parser.add_argument("--end", help="End time (ISO format, default: start + 1h)")
    parser.add_argument("--all-day", action="store_true", help="All-day event")
    parser.add_argument("--location", help="Event location name")
    parser.add_argument("--attendees", help="Comma-separated attendee open_ids")
    parser.add_argument("--no-notify", action="store_true", help="Don't notify attendees")
    parser.add_argument("--start-time", help="List filter: start time (ISO)")
    parser.add_argument("--end-time", help="List filter: end time (ISO)")
    parser.add_argument("--reminder", type=int, help="Reminder minutes before event (e.g. 15)")
    parser.add_argument("--recurrence", help="RFC 5545 RRULE (e.g. FREQ=WEEKLY;BYDAY=WE)")
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--page-token", help="Pagination token")
    parser.add_argument("--as-user", action="store_true",
                        help="Use user_access_token (creates event on user's calendar)")
    parser.add_argument("--brief", action="store_true",
                        help="Compact output for list-events: only event_id/summary/time/status")
    args = parser.parse_args()

    u = args.as_user

    if args.action == "list-calendars":
        result = list_calendars()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "get-primary":
        cal_id = get_primary_calendar_id(as_user=u)
        print(json.dumps({"calendar_id": cal_id}, ensure_ascii=False, indent=2))

    elif args.action == "create":
        if not args.summary or not args.start:
            print("ERROR: --summary and --start are required for create", file=sys.stderr)
            sys.exit(1)
        cal_id = args.calendar_id or get_primary_calendar_id(as_user=u)
        reminders = None
        if args.reminder is not None:
            reminders = [{"minutes": args.reminder}]
        event = create_event(cal_id, args.summary, args.start, args.end,
                             args.description, args.all_day, args.location, reminders,
                             args.recurrence, as_user=u)
        # Always add the current user as attendee so the event appears on their calendar.
        # Additional attendees from --attendees are merged in.
        user_id = os.getenv("TASKPOOL_USER_ID", "")
        attendee_ids = set()
        if user_id:
            attendee_ids.add(user_id)
        if args.attendees:
            for x in args.attendees.split(","):
                x = x.strip()
                if x:
                    attendee_ids.add(x)
        if attendee_ids and event.get("event_id"):
            add_attendees(cal_id, event["event_id"], list(attendee_ids), not args.no_notify, as_user=u)
        print(json.dumps(event, ensure_ascii=False, indent=2))

    elif args.action == "delete":
        if not args.event_id:
            print("ERROR: --event-id is required for delete", file=sys.stderr)
            sys.exit(1)
        cal_id = args.calendar_id or get_primary_calendar_id(as_user=u)
        result = delete_event(cal_id, args.event_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "list-events":
        cal_id = args.calendar_id or get_primary_calendar_id(as_user=u)
        result = list_events(cal_id, args.start_time, args.end_time,
                             args.page_size, args.page_token)
        if args.brief:
            result = _brief_events(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.action == "add-attendees":
        if not args.event_id or not args.attendees:
            print("ERROR: --event-id and --attendees are required for add-attendees", file=sys.stderr)
            sys.exit(1)
        cal_id = args.calendar_id or get_primary_calendar_id(as_user=u)
        ids = [x.strip() for x in args.attendees.split(",")]
        result = add_attendees(cal_id, args.event_id, ids, not args.no_notify, as_user=u)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
