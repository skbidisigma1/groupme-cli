"""Utility functions: realtime watch, export, stats, and helpers."""
from __future__ import annotations

import asyncio
import json
import time
from collections import Counter, defaultdict
from typing import Any, AsyncGenerator, Dict, Iterable, List, Optional

import requests
import websockets

PUSH_URL = "wss://push.groupme.com/faye"


async def watch_group(user_id: str, token: str, channels: List[str]) -> AsyncGenerator[Dict[str, Any], None]:
    """Connect to Faye and yield messages for subscribed channels.

    channels: e.g., [f"/user/{user_id}"]
    """
    # Faye Bayeux handshake and subscribe using websockets
    async with websockets.connect(PUSH_URL) as ws:
        # Handshake
        await ws.send(json.dumps({
            "channel": "/meta/handshake",
            "version": "1.0",
            "supportedConnectionTypes": ["websocket"],
            "ext": {"access_token": token, "timestamp": int(time.time())},
        }))
        resp_raw = await ws.recv()
        resp = json.loads(resp_raw)
        # Faye may send a list of messages; find the handshake reply
        if isinstance(resp, list):
            client_id = None
            for item in resp:
                if isinstance(item, dict) and item.get("channel") == "/meta/handshake" and item.get("clientId"):
                    client_id = item.get("clientId")
                    break
        else:
            client_id = resp.get("clientId")
        # Subscribe
        for ch in channels:
            await ws.send(json.dumps({
                "channel": "/meta/subscribe",
                "clientId": client_id,
                "subscription": ch,
            }))
            await ws.recv()  # ignore ack
        # Listen loop
        while True:
            raw = await ws.recv()
            data = json.loads(raw)
            # Messages may be a list of envelopes or a single envelope
            envelopes = data if isinstance(data, list) else [data]
            for env in envelopes:
                if not isinstance(env, dict):
                    continue
                payload = env.get("data")
                if payload is None and isinstance(env.get("ext"), dict) and env.get("ext").get("data"):
                    payload = env.get("ext").get("data")
                if payload is not None:
                    yield payload


def export_group_messages(client, group_id: str) -> Iterable[Dict[str, Any]]:
    """Iterate all messages in a group from newest to oldest until exhausted."""
    before_id: Optional[str] = None
    while True:
        resp = client.get_group_messages(group_id, limit=100, before_id=before_id)
        messages = resp.get("messages", []) if isinstance(resp, dict) else []
        if not messages:
            break
        for m in messages:
            yield m
        before_id = messages[-1]["id"]
        if len(messages) < 100:
            break


def stats_from_messages(messages: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute simple stats: top posters, most liked messages, hourly histogram."""
    count_by_user = Counter()
    likes_by_message: List[tuple[int, Dict[str, Any]]] = []
    hour_hist = Counter()
    for m in messages:
        name = m.get("name") or m.get("sender_id")
        count_by_user[name] += 1
        likes = len(m.get("favorited_by", []))
        likes_by_message.append((likes, m))
        try:
            ts = int(m.get("created_at") or 0)
            hour = (ts // 3600) % 24
            hour_hist[hour] += 1
        except Exception:
            pass
    likes_by_message.sort(reverse=True, key=lambda x: x[0])
    return {
        "top_posters": count_by_user.most_common(10),
        "most_liked": likes_by_message[:10],
        "hour_hist": sorted(hour_hist.items()),
    }
