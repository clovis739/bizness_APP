import json
from datetime import datetime, timezone

import requests

EXPO_PUSH_API_URL = "https://exp.host/--/api/v2/push/send"


def normalize_push_tokens(preferences: dict | None) -> list[dict]:
    if not isinstance(preferences, dict):
        return []

    tokens = preferences.get("push_tokens", [])
    if not isinstance(tokens, list):
        return []

    normalized = []
    for item in tokens:
        if isinstance(item, dict) and item.get("token"):
            normalized.append(item)
    return normalized


def merge_push_token(preferences: dict | None, *, token: str, platform: str) -> dict:
    current = preferences if isinstance(preferences, dict) else {}
    push_tokens = normalize_push_tokens(current)
    next_tokens = [item for item in push_tokens if item.get("token") != token]
    next_tokens.append(
        {
            "token": token,
            "platform": platform,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {**current, "push_tokens": next_tokens}


def remove_push_token(preferences: dict | None, *, token: str) -> dict:
    current = preferences if isinstance(preferences, dict) else {}
    push_tokens = normalize_push_tokens(current)
    next_tokens = [item for item in push_tokens if item.get("token") != token]
    return {**current, "push_tokens": next_tokens}


def extract_push_token_values(preferences: dict | None) -> list[str]:
    return [item["token"] for item in normalize_push_tokens(preferences) if item.get("token")]


def send_expo_push_notifications(*, push_tokens: list[str], title: str, body: str, data: dict | None = None) -> None:
    messages = [
        {
            "to": token,
            "title": title,
            "body": body,
            "sound": "default",
            "data": data or {},
        }
        for token in push_tokens
    ]

    if not messages:
        return

    response = requests.post(
        EXPO_PUSH_API_URL,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json",
        },
        data=json.dumps(messages),
        timeout=15,
    )
    response.raise_for_status()
