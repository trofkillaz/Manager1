import os
import json
import asyncio
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
import redis.asyncio as redis

load_dotenv()

REDIS_1 = os.getenv("REDIS_1")
REDIS_2 = os.getenv("REDIS_2")
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

# --- Redis connections ---
redis_booking = redis.from_url(REDIS_1, decode_responses=True)
redis_events = redis.from_url(REDIS_2, decode_responses=True)

# ==============================
# EVENT LISTENER
# ==============================

async def event_listener(app):
    print("Event listener started")

    while True:
        try:
            keys = []
            async for key in redis_events.scan_iter("event:*"):
                keys.append(key)

            for key in keys:
                raw = await redis_events.get(key)
                if not raw:
                    continue

                event = json.loads(raw)

                # --- NEW BOOKING ---
                if event.get("type") == "new_booking":
                    booking_id = event["booking_id"]

                    raw_booking = await redis_booking.get(f"booking:{booking_id}")
                    if not raw_booking:
                        await redis_events.delete(key)
                        continue

                    data = json.loads(raw_booking)

                    text = (
                        f"🆕 Новая заявка\n\n"
                        f"🛵 {data['scooter']}\n"
                        f"📆 {data['days']} дней\n"
                        f"💵 {data['total']}\n"
                        f"💰 Депозит: {data['deposit']}\n\n"
                        f"👤 {data['name']}\n"
                        f"🏨 {data['hotel']} | {data['room']}\n"
                        f"📞 {data['contact']}"
                    )

                    keyboard = [
                        [
                            InlineKeyboardButton(
                                "2 шлема",
                                callback_data=f"helmet:{booking_id}"
                            ),
                            InlineKeyboardButton(
                                "2 дождевика",
                                callback_data=f"rain:{booking_id}"
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "Завершить",
                                callback_data=f"complete:{booking_id}"
                            )
                        ]
                    ]

                    msg = await app.bot.send_message(
                        chat_id=GROUP_CHAT_ID,
                        text=text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )

                    data["group_message_id"] = msg.message_id
                    data["equipment"] = []

                    await redis_booking.set(
                        f"booking:{booking_id}",
                        json.dumps(data),
                        ex=120
                    )

                await redis_events.delete(key)

        except Exception as e:
            print("Listener error:", e)

        await asyncio.sleep(2)

# ==============================
# CALLBACK HANDLER
# ==============================

async def manager_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, booking_id = query.data.split(":")

    raw = await redis_booking.get(f"booking:{booking_id}")
    if not raw:
        await query.edit_message_text("⚠ Заявка устарела")
        return

    data = json.loads(raw)

    # --- EQUIPMENT ---
    if action == "helmet":
        if "2 шлема" not in data["equipment"]:
            data["equipment"].append("2 шлема")

    if action == "rain":
        if "2 дождевика" not in data["equipment"]:
            data["equipment"].append("2 дождевика")

    # --- COMPLETE ---
    if action == "complete":

        equipment_text = "\n".join(data["equipment"]) if data["equipment"] else "Без доп. комплектации"

        final_text = (
            f"✅ Заявка завершена\n\n"
            f"🛵 {data['scooter']}\n"
            f"📆 {data['days']} дней\n"
            f"💵 {data['total']}\n"
            f"💰 Депозит: {data['deposit']}\n\n"
            f"📦 Комплектация:\n{equipment_text}\n\n"
            f"👤 {data['name']}\n"
            f"🏨 {data['hotel']} | {data['room']}\n"
            f"📞 {data['contact']}"
        )

        # Отправляем событие клиентскому боту
        await redis_events.set(
            f"event:update:{booking_id}",
            json.dumps({
                "type": "booking_update",
                "booking_id": booking_id
            }),
            ex=120
        )

        await query.edit_message_text(final_text)

        return

    # Обновляем booking
    await redis_booking.set(
        f"booking:{booking_id}",
        json.dumps(data),
        ex=120
    )

# ==============================
# MAIN
# ==============================

async def post_init(app):
    asyncio.create_task(event_listener(app))

def main():
    app =