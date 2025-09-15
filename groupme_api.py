"""GroupMe API helper module.

This module provides a thin Pythonic wrapper around the GroupMe REST API
suitable for use in a command-line client. It focuses on the subset of
endpoints needed for listing groups, reading and sending group messages,
listing direct message chats, and sending direct messages.

Key design goals:
- Simplicity: no heavy abstractions, just helper methods.
- Safety: never log or expose the API token.
- Helpful errors: raise GroupMeAPIError with details.
- Pagination support for retrieving latest N messages.

The public interface is the GroupMeClient class.
"""
from __future__ import annotations

import os
import uuid
import time
import logging
from typing import Any, Dict, List, Optional
import requests

# Configure a basic logger (can be overridden by application code)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE = "https://api.groupme.com/v3"
IMAGE_BASE = "https://image.groupme.com"
OAUTH_BASE = "https://oauth.groupme.com"


class GroupMeAPIError(RuntimeError):
    """Raised when the GroupMe API returns an error response."""

    def __init__(self, status_code: int, message: str, *, url: str, body: Any | None = None):
        super().__init__(f"HTTP {status_code} for {url}: {message}")
        self.status_code = status_code
        self.url = url
        self.body = body


class GroupMeClient:
    """Simple API client for GroupMe.

    Parameters
    ----------
    token : str
        GroupMe API token. Must not be empty.
    timeout : float, optional
        Request timeout (seconds) for all HTTP calls.
    session : requests.Session | None, optional
        Provide a custom requests session (for tests / advanced usage).
    """

    def __init__(self, token: str, *, timeout: float = 15.0, session: Optional[requests.Session] = None):
        if not token:
            raise ValueError("Token must be provided")
        self._token = token
        self._timeout = timeout
        self._session = session or requests.Session()
        # Conservative default headers. Authorization header preferred for API base.
        self._session.headers.update({
            # Send both for maximum compatibility with documented variants.
            "Authorization": f"Bearer {self._token}",
            "X-Access-Token": self._token,
            "User-Agent": "groupme-cli/1.0",
            "Accept": "application/json",
        })

    # ----------------------------- Internal helpers -------------------------
    def _request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None,
                 json: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None,
                 raw: bool = False) -> Any:
        """Perform an HTTP request and return the JSON "response" section.

        GroupMe wraps actual data in a top-level {"meta": ..., "response": ...} object.
        This method extracts and returns only the "response" value unless `raw=True`.
        """
        url = f"{API_BASE}{path}"
        merged_headers = {}
        if headers:
            merged_headers.update(headers)
        try:
            resp = self._session.request(method, url, params=params, json=json, headers=merged_headers or None, timeout=self._timeout)
        except requests.RequestException as e:
            raise GroupMeAPIError(-1, f"Network error: {e}", url=url) from e

        if not resp.ok:
            # Try to extract an error message
            try:
                data = resp.json()
                err_msg = data.get("meta", {}).get("errors") or data.get("meta", {}).get("message") or resp.text
            except ValueError:
                err_msg = resp.text
                data = None
            raise GroupMeAPIError(resp.status_code, str(err_msg), url=url, body=data)

        if raw:
            return resp.json()
        try:
            data = resp.json()
        except ValueError as e:
            raise GroupMeAPIError(resp.status_code, f"Invalid JSON: {e}", url=url) from e
        return data.get("response")

    # ----------------------------- Public API methods -----------------------
    def list_groups(self, *, page: int | None = None, per_page: int | None = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if per_page is not None:
            params["per_page"] = per_page
        return self._request("GET", "/groups", params=params)

    def list_all_groups(self) -> List[Dict[str, Any]]:
        """Return all groups by traversing paginated results until empty page."""
        page = 1
        all_groups: List[Dict[str, Any]] = []
        while True:
            groups = self.list_groups(page=page)
            if not groups:
                break
            all_groups.extend(groups)
            page += 1
        return all_groups

    def list_former_groups(self, *, page: int | None = None, per_page: int | None = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if per_page is not None:
            params["per_page"] = per_page
        return self._request("GET", "/groups/former", params=params)

    def get_group(self, group_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/groups/{group_id}")

    def create_group(self, name: str, *, description: Optional[str] = None, share: Optional[bool] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"name": name}
        if description is not None:
            payload["description"] = description
        if share is not None:
            payload["share"] = bool(share)
        return self._request("POST", "/groups", json=payload)

    def update_group(self, group_id: str, *, name: Optional[str] = None, description: Optional[str] = None,
                     share: Optional[bool] = None, office_mode: Optional[bool] = None, image_url: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if share is not None:
            body["share"] = bool(share)
        if office_mode is not None:
            body["office_mode"] = bool(office_mode)
        if image_url is not None:
            body["image_url"] = image_url
        return self._request("POST", f"/groups/{group_id}/update", json=body)

    def leave_group(self, group_id: str) -> None:
        self._request("POST", f"/groups/{group_id}/leave")

    def destroy_group(self, group_id: str) -> None:
        self._request("POST", f"/groups/{group_id}/destroy")

    def rejoin_group(self, group_id: str) -> None:
        self._request("POST", f"/groups/{group_id}/join")

    def add_members(self, group_id: str, members: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Invite/add members. Each member can have user_id, phone_number, email, nickname.

        Returns an object containing a results_id to poll.
        """
        payload = {"members": members}
        return self._request("POST", f"/groups/{group_id}/members/add", json=payload)

    def get_members_results(self, group_id: str, results_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/groups/{group_id}/members/results/{results_id}")

    def remove_member(self, group_id: str, member_id: str) -> None:
        self._request("POST", f"/groups/{group_id}/members/{member_id}/remove")

    def get_group_messages_latest(self, group_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch latest `limit` messages for a group (most recent first).

        The API returns messages sorted newest-first. We accumulate by using
        `before_id` to paginate backwards until we have at least `limit` messages.
        """
        if limit <= 0:
            return []
        collected: List[Dict[str, Any]] = []
        before_id: Optional[str] = None
        remaining = limit
        while remaining > 0:
            batch_limit = min(100, remaining)
            params: Dict[str, Any] = {"limit": batch_limit}
            if before_id:
                params["before_id"] = before_id
            resp = self._request("GET", f"/groups/{group_id}/messages", params=params)
            messages = resp.get("messages", []) if isinstance(resp, dict) else []
            if not messages:
                break
            collected.extend(messages)
            remaining = limit - len(collected)
            before_id = messages[-1]["id"]
            if len(messages) < batch_limit:
                break  # No more pages
        return collected[:limit]

    def send_group_message(self, group_id: str, text: str, *, attachments: Optional[List[Dict[str, Any]]] = None,
                            source_guid: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        payload = {
            "message": {
                "source_guid": source_guid or str(uuid.uuid4()),
                "text": text,
                "attachments": attachments or [],
            }
        }
        if dry_run:
            return {"dry_run": True, "payload": payload}
        return self._request("POST", f"/groups/{group_id}/messages", json=payload)

    def list_chats(self, *, page: Optional[int] = None, per_page: Optional[int] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if per_page is not None:
            params["per_page"] = per_page
        return self._request("GET", "/chats", params=params)

    def get_group_messages(self, group_id: str, *, limit: int = 20, before_id: Optional[str] = None,
                            since_id: Optional[str] = None, after_id: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": min(max(limit, 1), 100)}
        if before_id:
            params["before_id"] = before_id
        if since_id:
            params["since_id"] = since_id
        if after_id:
            params["after_id"] = after_id
        return self._request("GET", f"/groups/{group_id}/messages", params=params)

    def search_group_messages(self, group_id: str, query: str, *, before_id: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"query": query}
        if before_id:
            params["before_id"] = before_id
        return self._request("GET", f"/groups/{group_id}/messages/search", params=params)

    def get_direct_messages(self, other_user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        # Similar pagination strategy as group messages.
        if limit <= 0:
            return []
        collected: List[Dict[str, Any]] = []
        before_id: Optional[str] = None
        remaining = limit
        while remaining > 0:
            batch_limit = min(100, remaining)
            params: Dict[str, Any] = {"other_user_id": other_user_id, "limit": batch_limit}
            if before_id:
                params["before_id"] = before_id
            resp = self._request("GET", "/direct_messages", params=params)
            messages = resp.get("direct_messages", []) if isinstance(resp, dict) else []
            if not messages:
                break
            collected.extend(messages)
            remaining = limit - len(collected)
            before_id = messages[-1]["id"]
            if len(messages) < batch_limit:
                break
        return collected[:limit]

    def get_direct_messages_raw(self, other_user_id: Optional[str] = None, *, limit: int = 20, before_id: Optional[str] = None,
                                since_id: Optional[str] = None, after_id: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"limit": min(max(limit, 1), 100)}
        if other_user_id:
            params["other_user_id"] = other_user_id
        if before_id:
            params["before_id"] = before_id
        if since_id:
            params["since_id"] = since_id
        if after_id:
            params["after_id"] = after_id
        return self._request("GET", "/direct_messages", params=params)

    def search_direct_messages(self, query: str, *, other_user_id: Optional[str] = None, max_pages: int = 10) -> Dict[str, Any]:
        """Client-side search across DMs.

        GroupMe does not document a DM search endpoint publicly. To provide a
        usable experience, we paginate recent DMs and filter messages by text
        containing the query (case-insensitive). Optionally limit to a user.
        Returns a dict with key "direct_messages" for parity with other calls.
        """
        results: List[Dict[str, Any]] = []
        before_id: Optional[str] = None
        pages = 0
        q = (query or "").lower()
        while pages < max_pages:
            resp = self.get_direct_messages_raw(other_user_id, limit=100, before_id=before_id)
            msgs = resp.get("direct_messages", []) if isinstance(resp, dict) else []
            if not msgs:
                break
            for m in msgs:
                text = (m.get("text") or "").lower()
                if q in text:
                    results.append(m)
            before_id = msgs[-1]["id"]
            pages += 1
            if len(msgs) < 100:
                break
        return {"direct_messages": results}

    def send_direct_message(self, recipient_id: str, text: str, *, source_guid: Optional[str] = None,
                             dry_run: bool = False) -> Dict[str, Any]:
        payload = {
            "direct_message": {
                "source_guid": source_guid or str(uuid.uuid4()),
                "recipient_id": recipient_id,
                "text": text,
            }
        }
        if dry_run:
            return {"dry_run": True, "payload": payload}
        return self._request("POST", "/direct_messages", json=payload)

    def like_message(self, group_id: str, message_id: str) -> None:
        self._request("POST", f"/messages/{group_id}/{message_id}/like")

    def unlike_message(self, group_id: str, message_id: str) -> None:
        self._request("POST", f"/messages/{group_id}/{message_id}/unlike")

    def get_me(self) -> Dict[str, Any]:
        return self._request("GET", "/users/me")

    def upload_image(self, file_path: str) -> str:
        """Upload an image and return the hosted URL.

        This is optional functionality. The image service uses a different base
        and requires header `X-Access-Token` instead of Authorization.
        """
        url = f"{IMAGE_BASE}/pictures"
        headers = {
            "X-Access-Token": self._token,
            "Content-Type": "image/jpeg",  # Simplified assumption.
        }
        with open(file_path, "rb") as f:
            data = f.read()
        try:
            resp = requests.post(url, headers=headers, data=data, timeout=self._timeout)
        except requests.RequestException as e:
            raise GroupMeAPIError(-1, f"Network error: {e}", url=url) from e
        if not resp.ok:
            try:
                j = resp.json()
                err = j.get("errors") or resp.text
            except ValueError:
                err = resp.text
            raise GroupMeAPIError(resp.status_code, f"Image upload failed: {err}", url=url)
        try:
            j = resp.json()
        except ValueError as e:
            raise GroupMeAPIError(resp.status_code, f"Invalid JSON: {e}", url=url) from e
        return j.get("payload", {}).get("url")

    # ----------------------------- Bots -------------------------------------
    def list_bots(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/bots")

    def create_bot(self, *, name: str, group_id: str, avatar_url: Optional[str] = None, callback_url: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "bot": {
                "name": name,
                "group_id": group_id,
            }
        }
        if avatar_url:
            payload["bot"]["avatar_url"] = avatar_url
        if callback_url:
            payload["bot"]["callback_url"] = callback_url
        return self._request("POST", "/bots", json=payload)

    def post_bot_message(self, bot_id: str, text: str, *, picture_url: Optional[str] = None, attachments: Optional[List[Dict[str, Any]]] = None) -> None:
        payload: Dict[str, Any] = {"bot_id": bot_id, "text": text}
        if picture_url:
            payload["picture_url"] = picture_url
        if attachments:
            payload["attachments"] = attachments
        self._request("POST", "/bots/post", json=payload)

    # ----------------------------- Pins & Announcements ---------------------
    def pin_message(self, group_id: str, message_id: str) -> None:
        self._request("POST", f"/groups/{group_id}/pins/{message_id}")

    def unpin_message(self, group_id: str, message_id: str) -> None:
        # Some docs mention DELETE; use DELETE here.
        return self._request("DELETE", f"/groups/{group_id}/pins/{message_id}")

    def create_announcement(self, group_id: str, announcement: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", f"/groups/{group_id}/announcements", json=announcement)

    # ----------------------------- OAuth helpers ---------------------------
    @staticmethod
    def build_oauth_authorize_url(client_id: str, *, redirect_uri: Optional[str] = None, state: Optional[str] = None) -> str:
        from urllib.parse import urlencode
        params: Dict[str, Any] = {"client_id": client_id}
        if redirect_uri:
            params["redirect_uri"] = redirect_uri
        if state:
            params["state"] = state
        return f"{OAUTH_BASE}/oauth/authorize?{urlencode(params)}"

    @staticmethod
    def exchange_oauth_token(client_id: str, client_secret: str, code: str, *, redirect_uri: Optional[str] = None, timeout: float = 15.0) -> Dict[str, Any]:
        url = f"{OAUTH_BASE}/oauth/token"
        data: Dict[str, Any] = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        }
        if redirect_uri:
            data["redirect_uri"] = redirect_uri
        try:
            resp = requests.post(url, data=data, timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise GroupMeAPIError(-1, f"OAuth error: {e}", url=url) from e
        try:
            return resp.json()
        except ValueError as e:
            raise GroupMeAPIError(resp.status_code, f"Invalid JSON: {e}", url=url) from e

    def destroy_bot(self, bot_id: str) -> None:
        self._request("POST", "/bots/destroy", json={"bot_id": bot_id})

    # ----------------------------- Bulk like helpers ----------------------
    def bulk_like(self, ids: List[Dict[str, str]]) -> Dict[str, Any]:
        """Best-effort bulk-like. Falls back to individual like calls.

        ids: list of {"conversation_id": group_id_or_dm_conversation, "message_id": id}
        Returns a summary dict.
        """
        ok = 0
        errors: List[Dict[str, Any]] = []
        for item in ids:
            try:
                conv = item.get("conversation_id") or ""
                mid = item.get("message_id") or ""
                if not conv or not mid:
                    raise ValueError("missing ids")
                # For groups, conversation_id is the group_id for this CLI.
                self.like_message(conv, mid)
                ok += 1
            except Exception as e:  # noqa: BLE001
                errors.append({"item": item, "error": str(e)})
        return {"ok": ok, "failed": len(errors), "errors": errors}

    def bulk_unlike(self, ids: List[Dict[str, str]]) -> Dict[str, Any]:
        ok = 0
        errors: List[Dict[str, Any]] = []
        for item in ids:
            try:
                conv = item.get("conversation_id") or ""
                mid = item.get("message_id") or ""
                if not conv or not mid:
                    raise ValueError("missing ids")
                self.unlike_message(conv, mid)
                ok += 1
            except Exception as e:  # noqa: BLE001
                errors.append({"item": item, "error": str(e)})
        return {"ok": ok, "failed": len(errors), "errors": errors}


def build_client_from_env() -> GroupMeClient:
    """Create a GroupMeClient using the GROUPME_TOKEN env variable.

    Raises
    ------
    SystemExit
        If the token is missing.
    """
    token = os.getenv("GROUPME_TOKEN")
    if not token:
        raise SystemExit("Missing GROUPME_TOKEN environment variable. Set it in .env or shell.")
    return GroupMeClient(token=token)
