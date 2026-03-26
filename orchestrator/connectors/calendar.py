"""
orchestrator/connectors/calendar.py
─────────────────────────────────────
Google Calendar connector for OpenClaw.

Auth:    Shared OAuth2 token with Gmail (same credentials.json / token.json).
         Calendar scopes are ADDED to the existing token — user re-consents once.

Scopes:
  readonly  → list, get, search events, list calendars, check free/busy
  events    → create, update, delete (all HIL-gated)

HIL note:
  create_event(), update_event(), delete_event(), add_attendee() are called
  ONLY by the HIL approver after human confirmation.
  The agent may only call read-only methods directly.
  All write intents are staged into ContextBundle via stage_for_hil().
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Full scope set: Gmail + Calendar (unified token)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",           # full calendar access
    "https://www.googleapis.com/auth/calendar.readonly",  # explicit read
]


@dataclass
class CalendarEvent:
    """Structured representation of a Google Calendar event."""
    event_id: str
    calendar_id: str
    title: str
    start: str           # ISO 8601
    end: str             # ISO 8601
    description: str = ""
    location: str = ""
    attendees: list[str] = field(default_factory=list)
    organizer: str = ""
    status: str = ""     # confirmed | tentative | cancelled
    meet_link: str = ""
    recurrence: list[str] = field(default_factory=list)
    all_day: bool = False
    html_link: str = ""

    def friendly_time(self, tz: str = "UTC") -> str:
        """Return a human-readable time range string."""
        try:
            if self.all_day:
                return f"All day — {self.start}"
            start_dt = datetime.fromisoformat(self.start.replace("Z", "+00:00"))
            end_dt   = datetime.fromisoformat(self.end.replace("Z", "+00:00"))
            local_tz = ZoneInfo(tz)
            start_local = start_dt.astimezone(local_tz)
            end_local   = end_dt.astimezone(local_tz)
            if start_local.date() == end_local.date():
                return f"{start_local.strftime('%a %b %d, %Y')}  {start_local.strftime('%I:%M %p')} – {end_local.strftime('%I:%M %p %Z')}"
            return f"{start_local.strftime('%a %b %d %I:%M %p')} – {end_local.strftime('%a %b %d %I:%M %p %Z')}"
        except Exception:
            return f"{self.start} – {self.end}"

    def to_summary(self, tz: str = "UTC") -> str:
        lines = [
            f"ID:          {self.event_id}",
            f"Title:       {self.title}",
            f"Time:        {self.friendly_time(tz)}",
            f"Calendar:    {self.calendar_id}",
        ]
        if self.location:
            lines.append(f"Location:    {self.location}")
        if self.description:
            lines.append(f"Description: {self.description[:200]}")
        if self.attendees:
            lines.append(f"Attendees:   {', '.join(self.attendees[:8])}")
        if self.meet_link:
            lines.append(f"Meet link:   {self.meet_link}")
        if self.recurrence:
            lines.append(f"Recurrence:  {self.recurrence[0]}")
        lines.append(f"Status:      {self.status}")
        return "\n".join(lines)


@dataclass
class FreeBusySlot:
    start: str
    end: str
    busy: bool

    def friendly(self, tz: str = "UTC") -> str:
        try:
            s = datetime.fromisoformat(self.start.replace("Z", "+00:00")).astimezone(ZoneInfo(tz))
            e = datetime.fromisoformat(self.end.replace("Z", "+00:00")).astimezone(ZoneInfo(tz))
            label = "BUSY" if self.busy else "FREE"
            return f"[{label}] {s.strftime('%a %b %d %I:%M %p')} – {e.strftime('%I:%M %p %Z')}"
        except Exception:
            return f"{'BUSY' if self.busy else 'FREE'} {self.start} – {self.end}"


class CalendarConnector:
    """
    Wraps the Google Calendar API.
    Uses the same OAuth2 credentials as GmailConnector — single sign-on.
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        token_path: Optional[str] = None,
        default_timezone: Optional[str] = None,
    ):
        self.credentials_path = credentials_path or os.getenv(
            "GOOGLE_CREDENTIALS_PATH", "config/credentials.json"
        )
        self.token_path = token_path or os.getenv(
            "GOOGLE_TOKEN_PATH", "config/token.json"
        )
        self.default_tz = default_timezone or os.getenv("CALENDAR_TIMEZONE", "UTC")
        self.service = self._authenticate()

    # ── Auth (shared with Gmail) ──────────────────────────────────────────────

    def _authenticate(self):
        """
        OAuth2 — same flow as Gmail.
        If an existing token lacks calendar scopes, user is prompted to re-consent.
        """
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None  # Force re-auth if refresh fails (e.g. new scopes)

            if not creds or not creds.valid:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"Google credentials not found at: {self.credentials_path}"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)

            os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())

        return build("calendar", "v3", credentials=creds)

    # ── Read ops (agent-safe, no HIL) ────────────────────────────────────────

    def list_calendars(self) -> list[dict]:
        """
        List all calendars the user has access to.
        Returns list of {id, summary, primary, accessRole}.
        """
        try:
            result = self.service.calendarList().list().execute()
            return [
                {
                    "id":          c["id"],
                    "summary":     c.get("summary", ""),
                    "primary":     c.get("primary", False),
                    "accessRole":  c.get("accessRole", ""),
                    "description": c.get("description", ""),
                }
                for c in result.get("items", [])
            ]
        except HttpError as e:
            raise RuntimeError(f"Calendar list_calendars error: {e}") from e

    def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 20,
        query: Optional[str] = None,
        single_events: bool = True,
        order_by: str = "startTime",
    ) -> list[CalendarEvent]:
        """
        List upcoming events in a calendar.

        Args:
            calendar_id:   Calendar ID (default: "primary").
            time_min:      ISO 8601 lower bound. Defaults to now.
            time_max:      ISO 8601 upper bound.
            max_results:   Max events to return (1–250).
            query:         Free-text search across event fields.
            single_events: Expand recurring events into individual instances.
            order_by:      "startTime" | "updated"
        """
        try:
            now = datetime.now(timezone.utc).isoformat()
            params = {
                "calendarId":    calendar_id,
                "maxResults":    min(max_results, 250),
                "singleEvents":  single_events,
                "orderBy":       order_by,
                "timeMin":       time_min or now,
            }
            if time_max:
                params["timeMax"] = time_max
            if query:
                params["q"] = query

            result = self.service.events().list(**params).execute()
            return [self._parse_event(e, calendar_id) for e in result.get("items", [])]
        except HttpError as e:
            raise RuntimeError(f"Calendar list_events error: {e}") from e

    def get_event(self, event_id: str, calendar_id: str = "primary") -> CalendarEvent:
        """Fetch a single event by ID."""
        try:
            e = self.service.events().get(
                calendarId=calendar_id, eventId=event_id
            ).execute()
            return self._parse_event(e, calendar_id)
        except HttpError as e:
            raise RuntimeError(f"Calendar get_event error: {e}") from e

    def search_events(
        self,
        query: str,
        calendar_id: str = "primary",
        max_results: int = 10,
        days_ahead: int = 90,
    ) -> list[CalendarEvent]:
        """
        Search events by text query within the next N days.
        Searches across title, description, location, and attendees.
        """
        now     = datetime.now(timezone.utc)
        time_max = (now + timedelta(days=days_ahead)).isoformat()
        return self.list_events(
            calendar_id=calendar_id,
            query=query,
            max_results=max_results,
            time_max=time_max,
        )

    def get_free_busy(
        self,
        emails: list[str],
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        timezone: str = "UTC",
    ) -> dict[str, list[FreeBusySlot]]:
        """
        Query free/busy status for one or more calendar users.

        Args:
            emails:   List of Google account emails to check.
            time_min: Start of window (ISO 8601). Defaults to now.
            time_max: End of window. Defaults to 7 days from now.
            timezone: IANA timezone string.

        Returns:
            Dict keyed by email → list of FreeBusySlot.
        """
        try:
            now      = datetime.now(tz=ZoneInfo(timezone))
            t_min    = time_min or now.isoformat()
            t_max    = time_max or (now + timedelta(days=7)).isoformat()

            body = {
                "timeMin": t_min,
                "timeMax": t_max,
                "timeZone": timezone,
                "items": [{"id": email} for email in emails],
            }
            result = self.service.freebusy().query(body=body).execute()
            calendars = result.get("calendars", {})

            out: dict[str, list[FreeBusySlot]] = {}
            for email in emails:
                busy_periods = calendars.get(email, {}).get("busy", [])
                out[email] = [
                    FreeBusySlot(start=p["start"], end=p["end"], busy=True)
                    for p in busy_periods
                ]
            return out
        except HttpError as e:
            raise RuntimeError(f"Calendar get_free_busy error: {e}") from e

    def find_free_slots(
        self,
        emails: list[str],
        duration_minutes: int = 60,
        days_ahead: int = 7,
        working_hours_start: int = 9,
        working_hours_end: int = 18,
        timezone: str = "UTC",
    ) -> list[dict]:
        """
        Find available meeting slots where ALL given attendees are free.

        Returns list of {start, end, duration_minutes} dicts.
        """
        tz       = ZoneInfo(timezone)
        now      = datetime.now(tz=tz)
        end_date = now + timedelta(days=days_ahead)

        free_busy = self.get_free_busy(
            emails=emails,
            time_min=now.isoformat(),
            time_max=end_date.isoformat(),
            timezone=timezone,
        )

        # Merge all busy periods across all attendees
        all_busy: list[tuple[datetime, datetime]] = []
        for slots in free_busy.values():
            for slot in slots:
                s = datetime.fromisoformat(slot.start.replace("Z", "+00:00")).astimezone(tz)
                e = datetime.fromisoformat(slot.end.replace("Z", "+00:00")).astimezone(tz)
                all_busy.append((s, e))
        all_busy.sort(key=lambda x: x[0])

        # Walk through working hours day by day, find gaps
        free_slots = []
        current = now.replace(
            hour=working_hours_start, minute=0, second=0, microsecond=0
        )
        if current < now:
            current = now

        while current < end_date and len(free_slots) < 10:
            if current.weekday() >= 5:  # Skip weekends
                current = (current + timedelta(days=1)).replace(
                    hour=working_hours_start, minute=0, second=0, microsecond=0
                )
                continue

            slot_end = current + timedelta(minutes=duration_minutes)
            work_end = current.replace(hour=working_hours_end, minute=0, second=0)

            if slot_end > work_end:
                current = (current + timedelta(days=1)).replace(
                    hour=working_hours_start, minute=0, second=0, microsecond=0
                )
                continue

            # Check if this slot overlaps any busy period
            overlap = any(
                not (slot_end <= busy_start or current >= busy_end)
                for busy_start, busy_end in all_busy
            )

            if not overlap:
                free_slots.append({
                    "start":            current.isoformat(),
                    "end":              slot_end.isoformat(),
                    "duration_minutes": duration_minutes,
                    "day":              current.strftime("%A %b %d"),
                    "time":             f"{current.strftime('%I:%M %p')} – {slot_end.strftime('%I:%M %p %Z')}",
                })
                current = slot_end  # Non-overlapping slots
            else:
                current += timedelta(minutes=30)  # Try 30-min steps

        return free_slots

    # ── Write ops (HIL-only — called from hil/cli_approver.py) ───────────────

    def create_event(
        self,
        title: str,
        start: str,
        end: str,
        calendar_id: str = "primary",
        description: str = "",
        location: str = "",
        attendees: Optional[list[str]] = None,
        timezone: str = "UTC",
        add_google_meet: bool = False,
        recurrence: Optional[list[str]] = None,
        send_notifications: bool = True,
    ) -> CalendarEvent:
        """
        Create a calendar event.  MUST only be called after HIL approval.

        Args:
            title:               Event title.
            start:               ISO 8601 start datetime.
            end:                 ISO 8601 end datetime.
            calendar_id:         Target calendar (default: "primary").
            description:         Event description / notes.
            location:            Physical or virtual location.
            attendees:           List of attendee email addresses.
            timezone:            IANA timezone.
            add_google_meet:     Auto-generate a Google Meet link.
            recurrence:          RRULE strings, e.g. ["RRULE:FREQ=WEEKLY;COUNT=4"]
            send_notifications:  Whether to email attendees.

        Returns:
            Created CalendarEvent.
        """
        try:
            body: dict = {
                "summary":     title,
                "description": description,
                "location":    location,
                "start":       {"dateTime": start, "timeZone": timezone},
                "end":         {"dateTime": end,   "timeZone": timezone},
            }
            if attendees:
                body["attendees"] = [{"email": e} for e in attendees]
            if recurrence:
                body["recurrence"] = recurrence
            if add_google_meet:
                body["conferenceData"] = {
                    "createRequest": {
                        "requestId": f"openclaw-{int(datetime.now().timestamp())}",
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                }

            kwargs: dict = {
                "calendarId": calendar_id,
                "body":       body,
                "sendNotifications": send_notifications,
            }
            if add_google_meet:
                kwargs["conferenceDataVersion"] = 1

            created = self.service.events().insert(**kwargs).execute()
            return self._parse_event(created, calendar_id)
        except HttpError as e:
            raise RuntimeError(f"Calendar create_event error: {e}") from e

    def update_event(
        self,
        event_id: str,
        updates: dict,
        calendar_id: str = "primary",
        send_notifications: bool = True,
    ) -> CalendarEvent:
        """
        Patch an existing event.  MUST only be called after HIL approval.

        Args:
            event_id:   The event to update.
            updates:    Dict of fields to change. Supports:
                        title, description, location, start, end,
                        attendees (list of emails), status.
            calendar_id: Calendar containing the event.
        """
        try:
            patch_body: dict = {}
            if "title"       in updates: patch_body["summary"]     = updates["title"]
            if "description" in updates: patch_body["description"] = updates["description"]
            if "location"    in updates: patch_body["location"]    = updates["location"]
            if "status"      in updates: patch_body["status"]      = updates["status"]
            if "start"       in updates:
                patch_body["start"] = {"dateTime": updates["start"], "timeZone": updates.get("timezone", "UTC")}
            if "end"         in updates:
                patch_body["end"]   = {"dateTime": updates["end"],   "timeZone": updates.get("timezone", "UTC")}
            if "attendees"   in updates:
                patch_body["attendees"] = [{"email": e} for e in updates["attendees"]]

            updated = self.service.events().patch(
                calendarId=calendar_id,
                eventId=event_id,
                body=patch_body,
                sendNotifications=send_notifications,
            ).execute()
            return self._parse_event(updated, calendar_id)
        except HttpError as e:
            raise RuntimeError(f"Calendar update_event error: {e}") from e

    def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_notifications: bool = True,
    ) -> bool:
        """
        Delete an event.  MUST only be called after HIL approval.
        Returns True on success.
        """
        try:
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
                sendNotifications=send_notifications,
            ).execute()
            return True
        except HttpError as e:
            raise RuntimeError(f"Calendar delete_event error: {e}") from e

    def respond_to_invite(
        self,
        event_id: str,
        response: str,
        calendar_id: str = "primary",
        send_notifications: bool = True,
    ) -> CalendarEvent:
        """
        RSVP to a calendar invitation.  MUST only be called after HIL approval.

        Args:
            event_id:  The event to respond to.
            response:  "accepted" | "declined" | "tentative"
        """
        try:
            event = self.service.events().get(
                calendarId=calendar_id, eventId=event_id
            ).execute()

            # Find self in attendees and update response
            my_email = self._get_my_email()
            for attendee in event.get("attendees", []):
                if attendee.get("self") or attendee.get("email") == my_email:
                    attendee["responseStatus"] = response
                    break

            updated = self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event,
                sendNotifications=send_notifications,
            ).execute()
            return self._parse_event(updated, calendar_id)
        except HttpError as e:
            raise RuntimeError(f"Calendar respond_to_invite error: {e}") from e

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_event(self, e: dict, calendar_id: str) -> CalendarEvent:
        start_obj = e.get("start", {})
        end_obj   = e.get("end",   {})

        start = start_obj.get("dateTime") or start_obj.get("date", "")
        end   = end_obj.get("dateTime")   or end_obj.get("date", "")
        all_day = "date" in start_obj and "dateTime" not in start_obj

        attendees = [
            a.get("email", "") for a in e.get("attendees", [])
            if not a.get("resource")  # skip room resources
        ]

        meet_link = ""
        conf = e.get("conferenceData", {})
        for entry in conf.get("entryPoints", []):
            if entry.get("entryPointType") == "video":
                meet_link = entry.get("uri", "")
                break

        return CalendarEvent(
            event_id    = e.get("id", ""),
            calendar_id = calendar_id,
            title       = e.get("summary", "(no title)"),
            start       = start,
            end         = end,
            description = e.get("description", ""),
            location    = e.get("location", ""),
            attendees   = attendees,
            organizer   = e.get("organizer", {}).get("email", ""),
            status      = e.get("status", ""),
            meet_link   = meet_link,
            recurrence  = e.get("recurrence", []),
            all_day     = all_day,
            html_link   = e.get("htmlLink", ""),
        )

    def _get_my_email(self) -> str:
        """Get the primary email of the authenticated user."""
        try:
            cal = self.service.calendars().get(calendarId="primary").execute()
            return cal.get("id", "")
        except Exception:
            return ""
