import os
import json
import logging
import redis.asyncio as redis

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)

# --------- ENV ---------

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set")

if not REDIS_URL:
    raise ValueError("REDIS_URL not set")

if not GROUP_CHAT_ID:
    raise ValueError("GROUP_CHAT_ID not set")

GROUP_CHAT_ID = int(GROUP_CHAT_ID)

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# --------- CHECK BOOKINGS ---------

async def check_bookings(context: ContextTypes.DEFAULT_TYPE):
    try:
        keys = await redis_client.keys("booking:*")

        for key in keys:
            raw = await redis_client.get(key)
            if not raw:
                continue

            data = json.loads(raw)

            if data.get("status") == "new":

                text = (
                    f"🆕 Новая заявка\n\n"
                    f"🛵 {data.get('scooter')}\n"
                    f"📆 {data.get('days')} дней\n"
                    f"💰 {data.get('total')} VND\n\n"
                    f"👤 {data.get('name')}\n"
                    f"📞 {data.get('contact')}"
                )

                keyboard = [[
                    InlineKeyboardButton(
                        "✅ Подтвердить",
                        callback_data=f"confirm:{data.get('booking_id')}"
                    )
                ]]

                await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )

                data["status"] = "sent"
                await redis_client.set(key, json.dumps(data))

    except Exception as e:
        logging.error(f"Error in check_bookings: {e}")


# --------- CONFIRM BOOKING ---------

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    booking_id = query.data.split(":")[1]
    key = f"booking:{booking_id}"

    raw = await redis_client.get(key)
    if not raw:
        await query.edit_message_text("❌ Заявка не найдена")
        return

    data = json.loads(raw)

    data["status"] = "confirmed"
    await redis_client.set(key, json.dumps(data))

    # Уведомляем клиента
    try:
        await context.bot.send_message(
            chat_id=int(data["client_id"]),
            text="✅ Ваше бронирование подтверждено!"
        )
    except Exception as e:
        logging.error(f"Failed to notify client: {e}")

    await query.edit_message_text("✅ Заявка подтверждена")


# --------- MAIN ---------

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CallbackQueryHandler(confirm, pattern="^confirm:"))

    # Проверяем Redis каждые 10 секунд
    app.job_queue.run_repeating(check_bookings, interval=10, first=5)

    app.run_polling()


if __name__ == "__main__":
    main()