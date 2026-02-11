import hmac
import hashlib
import json
import os
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Header, status
from telegram import Bot
from database import get_order_by_id, update_order_status

# Load variables from .env into the environment
load_dotenv()

app = FastAPI()

# Initialize Telegram bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in the .env file")

bot = Bot(token=TELEGRAM_BOT_TOKEN)

async def send_distrib_file(user_id: int):
    """
    Send dist/bot.zip file to user chat
    """
    file_path = "dist/bot.zip"

    # Check if file exists
    if not os.path.exists(file_path):
        print(f"File {file_path} not found")
        return False

    try:
        with open(file_path, 'rb') as file:
            await bot.send_document(
                chat_id=user_id,
                document=file,
                filename="bot.zip",
                caption="📦 Here is your bot distribution package"
            )
        print(f"Successfully sent {file_path} to user {user_id}")
        return True
    except Exception as e:
        print(f"Failed to send file to user {user_id}: {e}")
        return False

# Retrieve the secret and validate its existence
COINBASE_WEBHOOK_SECRET = os.getenv("COINBASE_WEBHOOK_SECRET")

if not COINBASE_WEBHOOK_SECRET:
    raise RuntimeError("COINBASE_WEBHOOK_SECRET is not set in the .env file")

def verify_coinbase_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verifies the HMAC-SHA256 signature from Coinbase."""
    if not signature:
        return False
    
    computed_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(computed_signature, signature)

@app.post("/webhook/coinbase")
async def coinbase_webhook(
    request: Request, 
    x_cc_webhook_signature: str = Header(None)
):
    raw_payload = await request.body()
    print("RAW PAYLOAD", raw_payload)
    
    if not verify_coinbase_signature(raw_payload, x_cc_webhook_signature, COINBASE_WEBHOOK_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid webhook signature"
        )

    try:
        event = json.loads(raw_payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Processing logic
    event_type = event.get("event", {}).get("type")
    event_data = event.get("event", {}).get("data", {})
    metadata = event_data.get("metadata", {})

    print(f"Received event: {event_type}")
    print(f"Event data: {event_data}")
    print(f"Metadata: {metadata}")

    # Search for order in database by order_id from metadata
    order_id = metadata.get("order_id")
    if not order_id:
        print("No order_id in metadata, skipping")
        return {"status": "success"}

    try:
        order_id = int(order_id)
    except (ValueError, TypeError):
        print(f"Invalid order_id format: {order_id}")
        return {"status": "success"}

    # Get order from database
    order = get_order_by_id(order_id)

    if order:
        user_id = order.user_id

        # Handle different event types
        match event_type:
            case "charge:pending":
                # Send message to user that order is pending
                message = f"💳 Your order #{order_id} payment is pending. Please complete the payment (approx. 5-20 minutes to confirm)."
                try:
                    await bot.send_message(chat_id=user_id, text=message)
                    print(f"Sent pending notification to user {user_id} for order {order_id}")
                except Exception as e:
                    print(f"Failed to send message to user {user_id}: {e}")

            case "charge:confirmed":
                # Update order status to 1 (confirmed)
                updated_order = update_order_status(order_id, 1)
                if updated_order:
                    print(f"Updated order {order_id} status to 1 (confirmed)")
                else:
                    print(f"Failed to update order {order_id} status")

                # Send message to user that order is successfully paid
                message = f"✅ Your order #{order_id} has been successfully paid! Thank you for your payment."
                try:
                    await bot.send_message(chat_id=user_id, text=message)
                    await send_distrib_file(user_id)                    
                    print(f"Sent confirmation notification to user {user_id} for order {order_id}")
                except Exception as e:
                    print(f"Failed to send message to user {user_id}: {e}")

            case "charge:failed":
                # Send message to user that payment failed
                message = f"❌ Payment for your order #{order_id} has failed. Please try again or contact support."
                try:
                    await bot.send_message(chat_id=user_id, text=message)
                    print(f"Sent failure notification to user {user_id} for order {order_id}")
                except Exception as e:
                    print(f"Failed to send message to user {user_id}: {e}")

            case _:
                print(f"Unhandled event type: {event_type}")
    else:
        print(f"Order {order_id} not found in database")

    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    
    # Запуск сервера
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,
        log_level="info"
    )
    