"""
WhatsApp channel adapter — Phase 5B stub.

Twilio webhook → normalise → IntakePayload → process_intake()

When Phase 5B starts, implement this file. Zero changes to intake_service.py.

Message types Twilio sends:
  - Text:  Body field in form data
  - Voice: MediaUrl0 pointing to .ogg audio file
  - Image: MediaUrl0 pointing to JPEG/PNG

TODO Phase 5B:
  1. Verify Twilio webhook signature (X-Twilio-Signature header)
  2. Download media from MediaUrl0 using Twilio credentials
  3. Route by MediaContentType0:
       audio/* → transcribe via whisper_service → IntakePayload
       image/* → OCR via gemini_ocr_service → IntakePayload
       text    → IntakePayload directly
  4. Call process_intake(payload)
  5. Reply to sender via Twilio MessagingResponse with confirmation
"""

from fastapi import APIRouter

router = APIRouter(prefix="/channels/whatsapp", tags=["channels-phase5b"])


@router.post("/webhook", include_in_schema=False)
async def whatsapp_webhook_stub():
    return {"status": "Phase 5B not yet implemented"}