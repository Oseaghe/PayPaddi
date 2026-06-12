# PayPaddi — WhatsApp Conversational Payments Assistant

A FastAPI backend that lets merchants create Korapay payment links, check transaction statuses, view sales summaries, and download PDF reports — entirely through WhatsApp text or voice messages.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [File Structure](#file-structure)
- [Setup](#setup)
- [Environment Variables](#environment-variables)
- [Running the Server](#running-the-server)
- [WhatsApp Configuration](#whatsapp-configuration)
- [Kora Webhook Configuration](#kora-webhook-configuration)
- [Bot Commands & Conversation Flows](#bot-commands--conversation-flows)
- [API Endpoints](#api-endpoints)
- [Database Schema](#database-schema)
- [Module Reference](#module-reference)
- [Dependencies](#dependencies)
- [Troubleshooting](#troubleshooting)

---

## Overview

PayPaddi is a single-backend service that bridges Meta's WhatsApp Cloud API with the Korapay payment gateway. Merchants send natural language messages (or voice notes) and the bot:

1. Parses the intent (create payment, check status, view summary, download PDF)
2. Creates a Korapay checkout link or queries the local database
3. Replies via WhatsApp with the result
4. Receives Kora webhook events to notify the merchant when a customer pays

Everything runs over a single ngrok tunnel — both the WhatsApp and Kora webhooks share the same FastAPI server on different paths.

---

## Architecture

```
WhatsApp (Meta Cloud API)
        │
        ▼
POST /webhooks/whatsapp   ◄──── text or voice message
        │
        ├── voice? → transcribe.py (local Whisper + ffmpeg)
        │
        └── intent.py (regex-based intent detection)
                │
                ├── create_payment  → kora.py → Korapay API → payment link → WhatsApp reply
                ├── check_payment   → db.py → status lookup → WhatsApp reply
                ├── summary         → db.py → aggregate query → WhatsApp reply
                └── pdf_report      → db.py → fpdf2 → whatsapp.py media upload → document

POST /webhooks/kora       ◄──── charge.success / charge.failed events
        │
        └── db.py (update payment status) → WhatsApp merchant notification
```

---

## File Structure

```
Kora_Hackathon/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, all routes, business logic, PDF generation
│   ├── db.py            # SQLite helpers (merchants, payments)
│   ├── intent.py        # Regex intent parser
│   ├── kora.py          # Korapay API client (payment link creation, webhook verification)
│   ├── whatsapp.py      # Meta Cloud API client (send_message, send_document)
│   └── transcribe.py    # Local OpenAI Whisper transcription for voice notes
├── requirements.txt
├── .env                 # Secret keys (not committed)
└── kora.db              # SQLite database (auto-created on first run)
```

---

## Setup

### Prerequisites

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/) — required by Whisper for audio decoding
  ```powershell
  winget install --id Gyan.FFmpeg
  # Restart your terminal after installation
  ```
- [ngrok](https://ngrok.com/) — for exposing the local server to Meta and Korapay webhooks

### Install dependencies

```bash
pip install -r requirements.txt
pip install git+https://github.com/openai/whisper.git
```

### Clone Whisper (already done if the above worked)

The Whisper model (`base`) is downloaded automatically on first voice note transcription.

---

## Environment Variables

Create a `.env` file in the project root:

```env
# Korapay
KORA_SECRET_KEY=sk_test_...
KORA_PUBLIC_KEY=pk_test_...
KORA_BASE_URL=https://api.korapay.com/merchant/api/v1

# Your ngrok public URL (no trailing slash)
APP_BASE_URL=https://your-ngrok-subdomain.ngrok-free.app

# WhatsApp / Meta Cloud API
WHATSAPP_TOKEN=EAAVj...           # Temporary token from Meta Developer Dashboard (~24h expiry)
WHATSAPP_PHONE_NUMBER_ID=1168...  # Phone number ID from Meta app dashboard
WHATSAPP_VERIFY_TOKEN=your_custom_verify_token
```

> **Token expiry**: The `WHATSAPP_TOKEN` from Meta's test environment expires roughly every 24 hours. Regenerate it from the Meta Developer Dashboard → WhatsApp → API Setup, and update `.env` then restart the server.

---

## Running the Server

```bash
# Start ngrok first (keep this terminal open)
ngrok http 8000

# Update APP_BASE_URL in .env with the ngrok URL, then start the server
uvicorn app.main:app --reload --port 8000
```

A single ngrok URL serves both webhook paths:
- `https://<ngrok-url>/webhooks/whatsapp` — for Meta
- `https://<ngrok-url>/webhooks/kora` — for Korapay

---

## WhatsApp Configuration

1. Go to [Meta Developer Dashboard](https://developers.facebook.com) → your app → WhatsApp → Configuration
2. Set **Webhook URL** to: `https://<ngrok-url>/webhooks/whatsapp`
3. Set **Verify Token** to the value of `WHATSAPP_VERIFY_TOKEN` in your `.env`
4. Subscribe to the **messages** webhook field
5. Under API Setup, copy the temporary access token into `WHATSAPP_TOKEN` in `.env`

---

## Kora Webhook Configuration

1. Log in to your [Korapay Dashboard](https://merchant.korapay.com)
2. Navigate to Settings → Webhooks
3. Set the webhook URL to: `https://<ngrok-url>/webhooks/kora`

Kora will POST `charge.success`, `charge.failed`, and `charge.cancelled` events to this endpoint. The server verifies the `x-korapay-signature` header using HMAC-SHA256.

---

## Bot Commands & Conversation Flows

### Quick Commands

| Message | Action |
|---------|--------|
| `1` | Start creating a payment link |
| `2` | View today's transaction summary |
| `3` | Download today's PDF report |

### Natural Language

The bot understands free-form messages:

```
"Create a payment link for ₦15,000"
"Generate a ₦50,000 charge for John Doe"
"Show my weekly sales"
"How much have I made this month?"
"Download PDF"
"Export report"
```

Paste any Korapay reference UUID to check its status:
```
"Check status of be26e7d7-9f8a-43f0-..."
"be26e7d7-9f8a-43f0-a1b2-c3d4e5f60718"
```

### Multi-step: Create Payment

If you don't include a customer name, the bot asks for one:

```
You:  Create payment link for ₦15,000
Bot:  What is the customer's name?
You:  Jane Obi
Bot:  Payment link created!
      Amount: ₦15,000
      Customer: Jane Obi
      Reference: <uuid>
      Share this link: https://checkout.korapay.com/...
```

### Summary Periods

The summary intent supports: `today`, `this week`, `this month`, `this quarter`, `this year`.

```
"Show my monthly revenue"
"How much did I make this week?"
```

### Voice Notes

Send a voice note and the bot transcribes it using local Whisper (`base` model) and processes it as a text message. Transcription runs on CPU using FP32.

### PDF Report

Sending `3`, `pdf`, `download`, or `export` generates and delivers a PDF document to WhatsApp with:
- Report date and total revenue
- Table: Customer | Reference | Amount (NGN) | Time | Status
- "No transactions recorded today." if the period has no data

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |
| `GET` | `/webhooks/whatsapp` | Meta webhook verification (hub challenge) |
| `POST` | `/webhooks/whatsapp` | Receive incoming WhatsApp messages |
| `POST` | `/webhooks/kora` | Receive Korapay payment event notifications |

---

## Database Schema

SQLite database at `kora.db` (project root, auto-created).

### `merchants`

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID |
| `phone` | TEXT UNIQUE | WhatsApp phone number (E.164 format) |
| `created_at` | TEXT | ISO 8601 UTC timestamp |

A merchant record is created automatically on first message from a phone number.

### `payments`

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID |
| `merchant_id` | TEXT FK | References `merchants.id` |
| `amount` | REAL | Payment amount in NGN |
| `customer_name` | TEXT | Customer's name (required) |
| `description` | TEXT | Optional narration |
| `reference` | TEXT UNIQUE | Korapay reference (same as `id`) |
| `payment_link` | TEXT | Korapay checkout URL |
| `status` | TEXT | `pending` / `completed` / `failed` |
| `created_at` | TEXT | ISO 8601 UTC timestamp |
| `updated_at` | TEXT | ISO 8601 UTC timestamp |

---

## Module Reference

### `app/main.py`
FastAPI application. Contains all route handlers and business logic functions:
- `handle_message(sender, text)` — routes parsed intent to the correct handler
- `_handle_check_payment(sender, reference)` — looks up a payment by UUID reference
- `_process_payment_request(sender, merchant, amount, customer_name, description)` — creates payment via Kora and replies
- `_process_summary(sender, merchant, period)` — fetches and formats transaction summary
- `_handle_pdf_report(sender, merchant)` — generates and sends PDF via WhatsApp
- `_generate_pdf(payments)` — builds the fpdf2 PDF document in memory
- `_notify_merchant(payment, status)` — sends success/failure push to merchant after webhook

Mid-conversation state (waiting for customer name) is stored in `_pending: dict[str, dict]` — an in-memory dict keyed by sender phone number. This resets on server restart.

### `app/db.py`
Plain `sqlite3` database layer. All timestamps stored as UTC ISO 8601 strings.
- `init_db()` — creates tables if they don't exist (called at server startup)
- `get_or_create_merchant(phone)` — idempotent merchant lookup/creation
- `create_payment(merchant_id, amount, customer_name, description)` — inserts a new `pending` payment row
- `update_payment(reference, status, payment_link=None)` — updates status and optionally the checkout URL
- `get_payment_by_reference(reference)` — single payment lookup by UUID
- `get_summary(merchant_id, period)` — returns `{total_revenue, successful, failed, pending}` counts
- `get_payments_for_period(merchant_id, period)` — returns full payment rows for PDF generation

### `app/intent.py`
Regex-based intent classifier. Detection order (important — prevents conflicts):
1. Numeric shortcuts (`1`, `2`, `3`)
2. UUID detection → `check_payment` (runs before amount regex to avoid false positives)
3. PDF keywords → `pdf_report`
4. Summary keywords → `summary`
5. Amount regex + payment keywords → `create_payment`
6. Fallback → `unknown`

### `app/kora.py`
Korapay API client.
- `create_payment_link(reference, amount, description, customer_name)` — POSTs to `/charges/initialize`, returns `checkout_url`
- `verify_webhook(payload, signature)` — HMAC-SHA256 verification of Kora webhook signature

### `app/whatsapp.py`
Meta Cloud API client (Graph API v18.0).
- `send_message(to, text)` — sends a WhatsApp text message
- `send_document(to, pdf_bytes, filename)` — uploads PDF to Meta media API, then sends as a document message

### `app/transcribe.py`
Local Whisper transcription. The model is a lazy singleton — loaded once on first use and reused.
- `transcribe_voice_note(media_id, access_token)` — downloads audio from Meta, saves to temp `.ogg`, transcribes with `whisper.base`, deletes temp file
- `_ensure_ffmpeg()` — adds `imageio_ffmpeg` bundled binary to PATH if system ffmpeg is not found

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn[standard]` | ASGI server |
| `httpx` | Async HTTP client (Meta API, Kora API, audio download) |
| `python-dotenv` | `.env` file loading |
| `python-multipart` | Form/multipart parsing for FastAPI |
| `pydantic` | Request/response validation |
| `fpdf2` | PDF generation |
| `imageio[ffmpeg]` | Bundled ffmpeg binaries (fallback if system ffmpeg missing) |
| `openai-whisper` | Local speech-to-text (installed from GitHub) |

---

## Troubleshooting

### No response from bot after sending a WhatsApp message
- Check the terminal for `[wa] send_message failed` — the `WHATSAPP_TOKEN` has likely expired. Regenerate it in the Meta Developer Dashboard and restart the server.
- Ensure ngrok is running and the webhook URL in Meta matches the current ngrok URL.

### Voice notes not transcribing — `[WinError 2]`
- `ffmpeg` is not on PATH. Install it: `winget install --id Gyan.FFmpeg` then restart your terminal.
- The `imageio[ffmpeg]` fallback in `transcribe.py` handles this automatically if installed.

### PDF shows "No transactions recorded today."
- No payments have been created through the bot today (UTC). The daily filter uses UTC midnight as the start boundary.
- Check the terminal for `[pdf] merchant=... found X payment(s) for today` to confirm the query result.

### `kora.db` is empty after restarting
- The DB path is resolved relative to `app/db.py`'s location, so it always lands at `<project_root>/kora.db`. If you see a fresh DB, confirm no second copy was created by running uvicorn from a different directory.

### Kora webhook signature mismatch
- The server logs `[webhook] Kora signature mismatch — processing anyway` but continues. This is informational; payments still update correctly.
- In test mode, Kora may not always send a signature.
