import os
import json
import asyncio
from dotenv import load_dotenv
from telegram import *
from telegram.ext import *
import redis.asyncio as redis

load_dotenv()

BOT_TOKEN = os.getenv("MANAGER_BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

redis_booking = redis.Redis(
    host=os.getenv("REDIS_HOST"),
    port=int(os.getenv("REDIS_PORT")),
    db=int(os.getenv("REDIS_DB_BOOKING")),
    decode_responses=True
)

redis_events = redis.Redis(
    host=os.getenv("REDIS_HOST"),
    port=int(os.getenv("REDIS_PORT")),
    db=int(os.getenv("REDIS_DB_EVENTS")),
    decode_responses=True
)

# ---------------- EVENT LISTENER ----------------

async def event_listener(app):
    while True:
        async for key in redis_events.scan_iter("event:*"):
            raw = await redis_events.get(key)
            if not raw:
                continue

            event = json.loads(raw)

            if event.get("type") != "new_booking":
                continue

            booking_id = event["booking_id"]
            raw_booking = await redis_booking.get(f"booking:{booking_id}")
            if not raw_booking:
                continue

            data = json.loads(raw_booking)

            text = (
                f"🆕 Новая заявка\n\n"
                f"🛵 {data['scooter']}\n"
                f"📆 {data['days']} дней\n"
                f"💵 {data['total']} VND\n"
                f"💰 Депозит: {data['deposit']}\n\n"
                f"👤 {data['name']}\n"
                f"🏨 {data['hotel']} | {data['room']}\n"
                f"📞 {data['contact']}"
            )

            keyboard = [[
                InlineKeyboardButton("2 шлема", callback_data=f"helmets:{booking_id}"),
                InlineKeyboardButton("2 дождевика", callback_data=f"rain:{booking_id}")
            ],
            [
                InlineKeyboardButton("Завершить", callback_data=f"complete:{booking_id}")
            ]]

            msg = await app.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            data["group_message_id"] = msg.message_id
            data["equipment"] = ""

            await redis_booking.set(
                f"booking:{booking_id}",
                json.dumps(data),
                ex=120
            )

            await redis_events.delete(key)

        await asyncio.sleep(2)

# ---------------- CALLBACK ----------------

async def manager_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, booking_id = query.data.split(":")
    raw = await redis_booking.get(f"booking:{booking_id}")
    if not raw:
        return

    data = json.loads(raw)

    if action == "helmets":
        data["equipment"] += "• 2 шлема\n"

    if action == "rain":
        data["equipment"] += "• 2 дождевика\n"

    if action == "complete":
        await redis_events.set(
            f"event:{booking_id}",
            json.dumps({
                "type": "booking_update",
                "booking_id": booking_id
            }),
            ex=120
        )

        await query.edit_message_text(
            "✅ Оплата подтверждена. Заявка завершена."
        )
        return

    await redis_booking.set(
        f"booking:{booking_id}",
        json.dumps(data),
        ex=120
    )

# ---------------- MAIN ----------------

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CallbackQueryHandler(manager_actions))
    app.post_init = lambda app: asyncio.create_task(event_listener(app))

    app.run_polling()

if __name__ == "__main__":
    main()