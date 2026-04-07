from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import requests


def management_publish_url(base_url: str, vhost: str, exchange: str) -> str:
    base = base_url.strip().rstrip("/")
    vhost_enc = quote(vhost, safe="")
    exchange_enc = quote(exchange, safe="")
    return f"{base}/api/exchanges/{vhost_enc}/{exchange_enc}/publish"


def build_publish_body_dict(payload: dict[str, Any], routing_key: str) -> dict[str, Any]:
    inner = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return {
        "properties": {},
        "routing_key": routing_key,
        "payload": inner,
        "payload_encoding": "string",
    }


def publish_body_json_for_clipboard(payload: dict[str, Any], routing_key: str) -> str:
    return json.dumps(
        build_publish_body_dict(payload, routing_key),
        ensure_ascii=False,
        indent=4,
    )


def publish_amq_default(
    base_url: str,
    username: str,
    password: str,
    payload: dict[str, Any],
    routing_key: str,
    *,
    vhost: str = "/",
    exchange: str = "amq.default",
    timeout: float = 30,
    verify: bool = True,
) -> tuple[bool, str]:
    url = management_publish_url(base_url, vhost, exchange)
    body_obj = build_publish_body_dict(payload, routing_key.strip() or "pickuptasks_queue")
    raw = json.dumps(body_obj, ensure_ascii=False, separators=(",", ":"))
    headers = {"Content-Type": "application/json"}
    auth = (username.strip(), password)
    try:
        r = requests.post(
            url,
            data=raw.encode("utf-8"),
            headers=headers,
            auth=auth,
            timeout=timeout,
            verify=verify,
        )
    except requests.RequestException as e:
        return False, str(e)
    text = (r.text or "").strip()
    if r.status_code >= 400:
        return False, f"HTTP {r.status_code} {url}\n{text[:1200]}"
    if not text:
        return True, "Đã gửi (HTTP 2xx, body rỗng)."
    try:
        data = r.json()
    except json.JSONDecodeError:
        return True, text[:500]
    if isinstance(data, dict) and "routed" in data and data["routed"] is False:
        return False, "RabbitMQ trả routed=false (queue/routing_key không khớp hoặc không có consumer binding)."
    return True, "Đã publish lên queue."
