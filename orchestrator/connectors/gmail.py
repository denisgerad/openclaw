"""
orchestrator/connectors/gmail.py
─────────────────────────────────
Gmail connector for OpenClaw.

Auth:    OAuth2 browser consent flow (token cached to config/token.json)
Scopes:  Read + modify (reply, trash) — intentionally NOT full delete
         to keep the blast radius of automated actions small.

HIL note:
  This module NEVER calls reply() or trash() directly from the agent.
  Those methods are called ONLY by the HIL approver (hil/cli_approver.py)
  after explicit human confirmation.  The agent can only call:
    - list_messages()
    - search_messages()
    - get_message()
    - get_thread()
  The orchestrator stages reply/delete into ContextBundle.draft_* fields.
"""

import os
import base64
import email as email_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from context.context_bundle import MailMeta

# Scopes — read + labels + send (send only used after HIL approval)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",   # needed for trash
]


class GmailConnector:
    """
    Wraps the Gmail API.  Instantiate once and pass to the agent's tool belt.
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        token_path: Optional[str] = None,
    ):
        self.credentials_path = credentials_path or os.getenv(
            "GOOGLE_CREDENTIALS_PATH", "config/credentials.json"
        )
        self.token_path = token_path or os.getenv(
            "GOOGLE_TOKEN_PATH", "config/token.json"
        )
        self.service = self._authenticate()

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _authenticate(self):
        """
        OAuth2 browser consent flow.
        - First run:  opens browser, saves token to token_path
        - Subsequent: loads cached token, refreshes automatically
        """
        creds = None

        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"Google credentials not found at: {self.credentials_path}\n"
                        "Download credentials.json from Google Cloud Console:\n"
                        "  APIs & Services → Credentials → OAuth 2.0 Client IDs → Download"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save token for next run
            os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())

        return build("gmail", "v1", credentials=creds)

    # ── Read / Search (agent-safe, no HIL required) ──────────────────────────

    def list_messages(
        self,
        max_results: int = 10,
        label_ids: Optional[list[str]] = None,
        query: Optional[str] = None,
    ) -> list[MailMeta]:
        """
        List recent messages from the inbox.

        Args:
            max_results:  How many messages to return (max 100).
            label_ids:    e.g. ["INBOX"], ["UNREAD"], ["SENT"]
            query:        Gmail search query string (same as Gmail search bar).

        Returns:
            List of MailMeta objects (lightweight, no body).
        """
        try:
            params = {
                "userId": "me",
                "maxResults": min(max_results, 100),
            }
            if label_ids:
                params["labelIds"] = label_ids
            if query:
                params["q"] = query

            result = self.service.users().messages().list(**params).execute()
            messages = result.get("messages", [])

            mail_list = []
            for msg in messages:
                meta = self._fetch_meta(msg["id"])
                if meta:
                    mail_list.append(meta)
            return mail_list

        except HttpError as e:
            raise RuntimeError(f"Gmail list_messages error: {e}") from e

    def search_messages(self, query: str, max_results: int = 10) -> list[MailMeta]:
        """
        Search Gmail with a query string.
        Supports full Gmail search syntax: from:, subject:, after:, before:, etc.

        Examples:
            search_messages("from:boss@company.com is:unread")
            search_messages("subject:invoice after:2024/01/01")
        """
        return self.list_messages(max_results=max_results, query=query)

    def get_message(self, message_id: str) -> dict:
        """
        Fetch the full content of a single message.

        Returns a dict with keys:
            meta        → MailMeta
            body_text   → plain text body
            body_html   → HTML body (if available)
        """
        try:
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            meta = self._parse_meta(msg)
            body_text, body_html = self._extract_body(msg)
            return {"meta": meta, "body_text": body_text, "body_html": body_html}
        except HttpError as e:
            raise RuntimeError(f"Gmail get_message error: {e}") from e

    def get_thread(self, thread_id: str) -> list[dict]:
        """
        Fetch all messages in a thread, ordered oldest→newest.
        Returns list of {sender, body_text, date} dicts — suitable for
        injecting into ContextBundle.thread_history.
        """
        try:
            thread = (
                self.service.users()
                .threads()
                .get(userId="me", id=thread_id, format="full")
                .execute()
            )
            messages = thread.get("messages", [])
            history = []
            for msg in messages:
                meta = self._parse_meta(msg)
                body_text, _ = self._extract_body(msg)
                history.append(
                    {
                        "role": "sender",
                        "sender": meta.sender,
                        "date": meta.date,
                        "content": body_text,
                    }
                )
            return history
        except HttpError as e:
            raise RuntimeError(f"Gmail get_thread error: {e}") from e

    # ── Write ops (called ONLY by HIL approver after human confirmation) ──────

    def send_new(
        self,
        to_address: str,
        subject: str,
        body: str,
    ) -> str:
        """
        Send a new email (not a reply).  MUST only be called from hil/cli_approver.py.

        Returns the sent message ID.
        """
        try:
            message = MIMEMultipart()
            message["to"] = to_address
            message["subject"] = subject
            message.attach(MIMEText(body, "plain"))
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            sent = (
                self.service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
            return sent["id"]
        except HttpError as e:
            raise RuntimeError(f"Gmail send error: {e}") from e

    def reply(
        self,
        original_message_id: str,
        thread_id: str,
        reply_body: str,
        reply_to_address: str,
        original_subject: str,
    ) -> str:
        """
        Send a reply.  MUST only be called from hil/cli_approver.py.

        Returns the sent message ID.
        """
        try:
            subject = (
                original_subject
                if original_subject.startswith("Re:")
                else f"Re: {original_subject}"
            )

            message = MIMEMultipart()
            message["to"] = reply_to_address
            message["subject"] = subject
            message["In-Reply-To"] = original_message_id
            message["References"] = original_message_id

            message.attach(MIMEText(reply_body, "plain"))

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            sent = (
                self.service.users()
                .messages()
                .send(userId="me", body={"raw": raw, "threadId": thread_id})
                .execute()
            )
            return sent["id"]
        except HttpError as e:
            raise RuntimeError(f"Gmail reply error: {e}") from e

    def trash(self, message_id: str) -> bool:
        """
        Move a message to Trash.  MUST only be called from hil/cli_approver.py.
        Uses trash (recoverable) not delete (permanent).

        Returns True on success.
        """
        try:
            self.service.users().messages().trash(
                userId="me", id=message_id
            ).execute()
            return True
        except HttpError as e:
            raise RuntimeError(f"Gmail trash error: {e}") from e

    # ── Private helpers ───────────────────────────────────────────────────────

    def _fetch_meta(self, message_id: str) -> Optional[MailMeta]:
        """Fetch message metadata only (no body) — fast."""
        try:
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="metadata",
                     metadataHeaders=["From", "To", "Subject", "Date"])
                .execute()
            )
            return self._parse_meta(msg)
        except HttpError:
            return None

    def _parse_meta(self, msg: dict) -> MailMeta:
        """Parse a Gmail message dict into a MailMeta object."""
        headers = {
            h["name"]: h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }
        has_attachments = any(
            part.get("filename")
            for part in msg.get("payload", {}).get("parts", [])
        )
        return MailMeta(
            message_id=msg["id"],
            thread_id=msg.get("threadId", ""),
            subject=headers.get("Subject", "(no subject)"),
            sender=headers.get("From", ""),
            recipients=headers.get("To", "").split(","),
            date=headers.get("Date", ""),
            snippet=msg.get("snippet", ""),
            labels=msg.get("labelIds", []),
            has_attachments=has_attachments,
        )

    def _extract_body(self, msg: dict) -> tuple[str, str]:
        """
        Extract plain text and HTML body from a full message.
        Handles both simple (non-multipart) and multipart messages.
        """
        body_text = ""
        body_html = ""
        payload = msg.get("payload", {})

        def decode_part(data: str) -> str:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

        def walk_parts(parts):
            nonlocal body_text, body_html
            for part in parts:
                mime = part.get("mimeType", "")
                data = part.get("body", {}).get("data", "")
                if mime == "text/plain" and data and not body_text:
                    body_text = decode_part(data)
                elif mime == "text/html" and data and not body_html:
                    body_html = decode_part(data)
                elif "parts" in part:
                    walk_parts(part["parts"])

        if "parts" in payload:
            walk_parts(payload["parts"])
        else:
            data = payload.get("body", {}).get("data", "")
            mime = payload.get("mimeType", "")
            if data:
                if mime == "text/html":
                    body_html = decode_part(data)
                else:
                    body_text = decode_part(data)

        return body_text, body_html
