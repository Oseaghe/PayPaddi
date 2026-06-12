import os
from contextlib import asynccontextmanager
from datetime import date
from fastapi import FastAPI, Request, Query, Header
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

load_dotenv()

from app.db import (
    init_db, get_or_create_merchant, create_payment, update_payment,
    get_payment_by_reference, get_summary, get_payments_for_period, get_conn,
)
from app.kora import create_payment_link, verify_webhook
from app.whatsapp import send_message, send_document
from app.intent import detect_intent
from app.transcribe import transcribe_voice_note

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")

# Mid-conversation state: sender -> {step, amount, description}
_pending: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Kora Payments Bot", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


# --- WhatsApp Webhook ---

@app.get("/webhooks/whatsapp")
def verify_whatsapp(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Forbidden", status_code=403)


@app.post("/webhooks/whatsapp")
async def receive_whatsapp(request: Request):
    payload = await request.json()

    try:
        value = payload["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError):
        return {"status": "ok"}

    messages = value.get("messages", [])
    if not messages:
        return {"status": "ok"}

    message = messages[0]
    sender = message["from"]
    msg_type = message.get("type")
    print(f"[wa] message from {sender}, type={msg_type}")

    if msg_type == "text":
        text = message["text"]["body"]
    elif msg_type in ("audio", "voice"):
        media_id = message[msg_type]["id"]
        try:
            text = await transcribe_voice_note(media_id, WHATSAPP_TOKEN)
        except Exception as e:
            print(f"[wa] transcription error: {e}")
            await send_message(sender, "Sorry, I couldn't understand your voice note. Please try typing instead.")
            return {"status": "ok"}
        if not text:
            await send_message(sender, "Sorry, I couldn't understand your voice note. Please try typing instead.")
            return {"status": "ok"}
    else:
        return {"status": "ok"}

    try:
        await handle_message(sender, text)
    except Exception as e:
        print(f"[wa] handle_message error: {e}")

    return {"status": "ok"}


async def handle_message(sender: str, text: str):
    merchant = get_or_create_merchant(sender)

    # Handle mid-conversation state (waiting for customer name)
    if sender in _pending:
        state = _pending.pop(sender)
        if state["step"] == "awaiting_name":
            await _process_payment_request(
                sender, merchant, state["amount"], text.strip(), state.get("description")
            )
            return

    parsed = detect_intent(text)

    if parsed["intent"] == "check_payment":
        await _handle_check_payment(sender, parsed["reference"])

    elif parsed["intent"] == "create_payment":
        if not parsed["amount"]:
            await send_message(
                sender,
                "How much is the payment?\n\nExample: *Create payment link for ₦15,000*",
            )
            return
        if not parsed.get("customer_name"):
            _pending[sender] = {
                "step": "awaiting_name",
                "amount": parsed["amount"],
                "description": parsed.get("description"),
            }
            await send_message(sender, "What is the customer's name?")
            return
        await _process_payment_request(
            sender, merchant, parsed["amount"],
            parsed["customer_name"], parsed.get("description"),
        )

    elif parsed["intent"] == "summary":
        await _process_summary(sender, merchant, parsed.get("period", "daily"))

    elif parsed["intent"] == "pdf_report":
        await _handle_pdf_report(sender, merchant)

    else:
        await send_message(
            sender,
            "Welcome to PayPaddi!\n\n"
            "Send:\n"
            "*1* – Create a payment link\n"
            "*2* – View transaction summary\n"
            "*3* – Download today's PDF report\n\n"
            "Or just tell me what you need:\n"
            "• \"Create a payment link for ₦15,000\"\n"
            "• \"Show my weekly sales\"\n"
            "• Paste a reference ID to check its status",
        )


async def _handle_check_payment(sender: str, reference: str):
    payment = get_payment_by_reference(reference)
    if not payment:
        await send_message(sender, f"No payment found with reference:\n{reference}")
        return

    icons = {"completed": "✅", "failed": "❌", "pending": "⏳"}
    icon = icons.get(payment["status"], "•")
    created = payment["created_at"][:19].replace("T", " ")

    msg = (
        f"{icon} Payment Status\n\n"
        f"Status: {payment['status'].upper()}\n"        
        f"Amount: ₦{payment['amount']:,.0f}\n"
        f"Customer: {payment.get('customer_name') or '—'}\n"        
        f"Created: {created}\n"
        f"Reference: {payment['reference']}\n"
    )
    if payment.get("payment_link") and payment["status"] == "pending":
        msg += f"\n\nLink (still active):\n{payment['payment_link']}"

    await send_message(sender, msg)


async def _process_payment_request(
    sender: str, merchant: dict, amount: float,
    customer_name: str = None, description: str = None,
):
    payment = create_payment(merchant["id"], amount, customer_name, description)
    try:
        link = await create_payment_link(
            reference=payment["reference"],
            amount=amount,
            description=description or "Payment request",
            customer_name=customer_name,
        )
        update_payment(payment["reference"], "pending", link)

        msg = f"Payment link created!\n\nAmount: ₦{amount:,.0f}\nCustomer: {customer_name}"
        if description:
            msg += f"\nFor: {description}"
        msg += f"\nReference: {payment['reference']}"
        msg += f"\n\nShare this link with your customer:\n{link}"
        await send_message(sender, msg)
    except Exception as e:
        update_payment(payment["reference"], "failed")
        print(f"[payment] Kora error: {e}")
        await send_message(
            sender,
            f"Could not create payment link. Please try again.\n\n"
            f"Amount: ₦{amount:,.0f}\n"
            f"Reference: {payment['reference']}",
        )


async def _process_summary(sender: str, merchant: dict, period: str):
    data = get_summary(merchant["id"], period)
    period_labels = {
        "daily": "Today", "weekly": "This Week", "monthly": "This Month",
        "quarterly": "This Quarter", "yearly": "This Year",
    }
    label = period_labels.get(period, period.title())
    msg = (
        f"📊 {label}'s Summary\n\n"
        f"Revenue: ₦{data['total_revenue']:,.0f}\n"
        f"Successful Payments: {data['successful']}\n"
        f"Failed Payments: {data['failed']}\n"
        f"Pending Payments: {data['pending']}"
    )
    await send_message(sender, msg)


async def _handle_pdf_report(sender: str, merchant: dict):
    payments = get_payments_for_period(merchant["id"], "daily")
    print(f"[pdf] merchant={merchant['id']} phone={merchant['phone']} found {len(payments)} payment(s) for today")
    pdf_bytes = _generate_pdf(payments)
    today_str = date.today().strftime("%Y-%m-%d")
    await send_message(sender, f"Generating your report for {today_str}...")
    await send_document(sender, pdf_bytes, f"report_{today_str}.pdf")


def _generate_pdf(payments: list) -> bytes:
    from fpdf import FPDF

    today_str = date.today().strftime("%B %d, %Y")
    completed = [p for p in payments if p["status"] == "completed"]
    total_revenue = sum(p["amount"] for p in completed)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Daily Transaction Report", ln=True, align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, today_str, ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8,
        f"Total Revenue: NGN {total_revenue:,.0f}   |   "
        f"Transactions: {len(payments)}   |   "
        f"Successful: {len(completed)}",
        ln=True,
    )
    pdf.ln(4)

    col_w = [42, 52, 28, 28, 22]
    headers = ["Customer", "Reference", "Amount (NGN)", "Time", "Status"]

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(40, 40, 40)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 8, h, border=1, fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)

    pdf.set_font("Helvetica", "", 8)
    for idx, p in enumerate(payments):
        fill = idx % 2 == 0
        pdf.set_fill_color(245, 245, 245)
        customer = (p.get("customer_name") or "-")[:22]
        ref = p["reference"][:20] + "..."
        amount = f"{p['amount']:,.0f}"
        time_str = p["created_at"][11:16] if len(p["created_at"]) > 11 else "-"
        status = p["status"]
        pdf.cell(col_w[0], 7, customer, border=1, fill=fill)
        pdf.cell(col_w[1], 7, ref, border=1, fill=fill)
        pdf.cell(col_w[2], 7, amount, border=1, fill=fill, align="R")
        pdf.cell(col_w[3], 7, time_str, border=1, fill=fill, align="C")
        pdf.cell(col_w[4], 7, status, border=1, fill=fill, align="C")
        pdf.ln()

    if not payments:
        pdf.ln(4)
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 10, "No transactions recorded today.", ln=True, align="C")

    return bytes(pdf.output())


# --- Kora Webhook ---

@app.post("/webhooks/kora")
async def kora_webhook(
    request: Request,
    x_kora_signature: str = Header(None, alias="x-korapay-signature"),
):
    payload = await request.json()
    event = payload.get("event")
    data = payload.get("data", {})

    if x_kora_signature and not verify_webhook(data, x_kora_signature):
        print("[webhook] Kora signature mismatch — processing anyway")

    reference = (
        data.get("payment_reference")
        or data.get("reference")
        or data.get("transaction_reference")
    )
    if not reference:
        return {"status": "ok"}

    payment = get_payment_by_reference(reference)
    if not payment or payment["status"] != "pending":
        return {"status": "ok"}

    if event == "charge.success":
        update_payment(reference, "completed")
        await _notify_merchant(payment, "completed")
    elif event in ("charge.failed", "charge.cancelled"):
        update_payment(reference, "failed")
        await _notify_merchant(payment, "failed")

    return {"status": "ok"}


async def _notify_merchant(payment: dict, status: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT phone FROM merchants WHERE id = ?", (payment["merchant_id"],)
        ).fetchone()
    if not row:
        return

    amount = payment["amount"]
    customer = payment.get("customer_name") or "Customer"
    reference = payment["reference"]

    if status == "completed":
        msg = (
            f"✅ Payment received!\n\n"
            f"Amount: ₦{amount:,.0f}\n"
            f"Customer: {customer}\n"
            f"Reference: {reference}"
        )
    else:
        msg = (
            f"❌ Payment failed or expired.\n\n"
            f"Amount: ₦{amount:,.0f}\n"
            f"Customer: {customer}\n"
            f"Reference: {reference}"
        )

    await send_message(row["phone"], msg)
