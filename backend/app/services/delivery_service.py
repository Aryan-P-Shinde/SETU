"""
Delivery service — sends approved briefs to volunteers.

V1 channels:
  - FCM push notification (in-app, Firebase Cloud Messaging)

V1.1 channels (plug in here, zero changes to router or brief_service):
  - WhatsApp via Twilio
  - WhatsApp via Meta Cloud API

Design: DeliveryService is a thin dispatcher. Each channel is a strategy.
Adding WhatsApp = add a new _send_whatsapp() function and one elif branch.

FCM token management:
  Volunteer app stores the FCM token in Firestore on first launch:
    volunteers/{id}/fcm_token: str
  This service reads that field when sending.
"""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class DeliveryChannel(str, Enum):
    fcm       = "fcm"        # Firebase Cloud Messaging (V1 — in-app push)
    whatsapp  = "whatsapp"   # V1.1
    sms       = "sms"        # V1.1 fallback


@dataclass
class DeliveryResult:
    success: bool
    channel: DeliveryChannel
    message_id: Optional[str] = None
    error: Optional[str] = None


async def deliver_brief(
    brief_text: str,
    map_link: Optional[str],
    volunteer_id: str,
    dispatch_id: str,
    fcm_token: Optional[str] = None,
) -> DeliveryResult:
    """
    Send an approved brief to a volunteer.

    V1: FCM push only.
    V1.1: add whatsapp/sms as fallback if fcm_token is None.

    Never raises — returns DeliveryResult(success=False) on failure
    so the router can store the error and still mark brief as sent.
    """
    if fcm_token:
        return await _send_fcm(brief_text, map_link, fcm_token, dispatch_id)

    # V1.1 hook — whatsapp/SMS fallback when no FCM token
    # if volunteer_phone:
    #     return await _send_whatsapp(brief_text, map_link, volunteer_phone)

    logger.warning(
        f"No FCM token for volunteer {volunteer_id} — brief not pushed. "
        f"Volunteer will see it on next app open."
    )
    return DeliveryResult(
        success=False,
        channel=DeliveryChannel.fcm,
        error="No FCM token registered for this volunteer",
    )


async def _send_fcm(
    brief_text: str,
    map_link: Optional[str],
    fcm_token: str,
    dispatch_id: str,
) -> DeliveryResult:
    """
    Send FCM notification via Firebase Cloud Messaging HTTP v1 API.

    Auth: uses Application Default Credentials (Cloud Run handles this).
    For local dev: set GOOGLE_APPLICATION_CREDENTIALS in .env.
    """
    from app.core.config import settings
    project_id = settings.FIREBASE_PROJECT_ID
    if not project_id:
        return DeliveryResult(
            success=False,
            channel=DeliveryChannel.fcm,
            error="FIREBASE_PROJECT_ID not set",
        )

    # Truncate brief for notification body (FCM limit ~1000 chars, but keep UX tight)
    preview = brief_text[:200] + "…" if len(brief_text) > 200 else brief_text

    payload = {
        "message": {
            "token": fcm_token,
            # Notification block — shown in system tray even when app is background
            "notification": {
                "title": "🚨 New Mission Brief",
                "body": preview,
            },
            # Data block — always delivered, app reads this to deep-link
            "data": {
                "dispatch_id": dispatch_id,
                "type": "brief",
                "map_link": map_link or "",
            },
            # Android-specific: high priority wakes device immediately
            "android": {
                "priority": "HIGH",
                "notification": {
                    "channel_id": "missions",   # must be registered in volunteer app
                    "sound": "default",
                },
            },
            # APNS (iOS) — not in scope for v1 but harmless to include
            "apns": {
                "payload": {
                    "aps": {
                        "alert": {"title": "New Mission", "body": preview},
                        "sound": "default",
                        "badge": 1,
                    }
                }
            },
        }
    }

    try:
        access_token = await _get_fcm_access_token()
        url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        message_id = data.get("name", "")
        logger.info(f"FCM sent: dispatch={dispatch_id} message_id={message_id}")
        return DeliveryResult(
            success=True,
            channel=DeliveryChannel.fcm,
            message_id=message_id,
        )

    except httpx.HTTPStatusError as e:
        error = f"FCM HTTP {e.response.status_code}: {e.response.text[:200]}"
        logger.error(f"FCM send failed: {error}")
        return DeliveryResult(success=False, channel=DeliveryChannel.fcm, error=error)

    except Exception as e:
        logger.error(f"FCM send unexpected error: {e}")
        return DeliveryResult(success=False, channel=DeliveryChannel.fcm, error=str(e))


async def _get_fcm_access_token() -> str:
    """
    Get a short-lived OAuth2 access token for FCM HTTP v1 API.
    Uses google-auth library with Application Default Credentials.
    On Cloud Run this is automatic. Local dev needs GOOGLE_APPLICATION_CREDENTIALS.
    """
    try:
        import google.auth
        import google.auth.transport.requests

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/firebase.messaging"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token
    except Exception as e:
        raise RuntimeError(f"Could not obtain FCM access token: {e}") from e


# ── V1.1 stubs (implement here when ready) ───────────────────────────────────

async def _send_whatsapp(
    brief_text: str,
    map_link: Optional[str],
    phone: str,
) -> DeliveryResult:
    """
    V1.1: Send brief via Twilio WhatsApp API.
    Implement when Twilio credentials are available.
    Same interface as _send_fcm — DeliveryResult returned either way.
    """
    # account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    # auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
    # from_number = os.getenv("TWILIO_WHATSAPP_FROM")
    # message = f"{brief_text}\n\n📍 {map_link}" if map_link else brief_text
    # ...POST to https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json
    raise NotImplementedError("WhatsApp delivery — Phase V1.1")