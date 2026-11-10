"""Notification delivery (Web Push / VAPID). Every attempt, retry and failure is logged.

In-app alert history is the reliable record; push delivery is best-effort and OS-dependent.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, insert, select

from market_sage.core.config import Settings
from market_sage.core.timeutil import utcnow
from market_sage.db import schema as s

SendFn = Callable[[dict[str, Any], str], None]  # (subscription_info, payload_json) -> raises on failure


class PushGone(Exception):
    """Subscription expired/unsubscribed (HTTP 404/410): deactivate it."""


def webpush_sender(settings: Settings) -> SendFn | None:
    if not (settings.vapid_private_key and settings.vapid_public_key):
        return None
    from pywebpush import WebPushException, webpush

    def send(sub: dict[str, Any], payload: str) -> None:
        try:
            webpush(subscription_info=sub, data=payload,
                    vapid_private_key=settings.vapid_private_key.get_secret_value(),  # type: ignore[union-attr]
                    vapid_claims={"sub": settings.vapid_subject}, ttl=3600)
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                raise PushGone(str(exc)) from exc
            raise

    return send


@dataclass
class DeliveryResult:
    sent: int = 0
    failed: int = 0
    skipped: int = 0


class Notifier:
    def __init__(self, engine: Engine, sender: SendFn | None, max_attempts: int = 3,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.engine, self.sender, self.max_attempts, self.sleep = engine, sender, max_attempts, sleep

    def _log(self, alert_id: int, sub_id: int | None, attempt: int, status: str, error: str | None = None) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(s.notification_deliveries).values(alert_id=alert_id, channel="webpush",
                                                                  subscription_id=sub_id, attempt=attempt,
                                                                  status=status, created_at=utcnow(), error=error))

    def deliver(self, alert: dict[str, Any]) -> DeliveryResult:
        res = DeliveryResult()
        with self.engine.connect() as conn:
            subs = conn.execute(select(s.push_subscriptions).where(s.push_subscriptions.c.active.is_(True))).fetchall()
        if self.sender is None or not subs:
            self._log(alert["id"], None, 1, "skipped",
                      "push not configured (VAPID keys missing)" if self.sender is None else "no active subscriptions")
            res.skipped += 1
            return res
        payload = json.dumps({"title": f"[{alert['stage'].replace('_', ' ').upper()}] {alert['title']}",
                              "body": alert["message"][:240], "alert_id": alert["id"], "url": "/alerts"})
        for sub in subs:
            info = {"endpoint": sub.endpoint, "keys": sub.keys}
            for attempt in range(1, self.max_attempts + 1):
                try:
                    self.sender(info, payload)
                    self._log(alert["id"], sub.id, attempt, "sent")
                    res.sent += 1
                    break
                except PushGone as exc:
                    self._log(alert["id"], sub.id, attempt, "failed", f"subscription gone: {exc}")
                    with self.engine.begin() as conn:
                        conn.execute(s.push_subscriptions.update().where(s.push_subscriptions.c.id == sub.id)
                                     .values(active=False))
                    res.failed += 1
                    break
                except Exception as exc:  # noqa: BLE001 - every failure is recorded
                    self._log(alert["id"], sub.id, attempt, "failed", f"{type(exc).__name__}: {exc}"[:500])
                    if attempt == self.max_attempts:
                        res.failed += 1
                    else:
                        self.sleep(2 ** attempt)
        return res
