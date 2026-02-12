import os
import json
import asyncio
import logging
import redis.asyncio as redis

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")
MANAGER_CHAT_ID = int(os.getenv("MANAGER_CHAT_ID"))

redis_client = redis.from_url(REDIS_URL, decode_responses=True)


# ---------- CHECK BOOKINGS ----------

async def check_bookings(context: ContextTypes.DEFAULT_TYPE):
    keys = await redis_client.keys("booking:*")

    for key in keys:
        data = json.loads(await redis_client.get(key))

        if data["status"] == "new":

            text = (
                f"🆕 Новая заявка\n\n"
                f"🛵 {data['scooter']}\n"
                f"📆 {data['days']} дней\n"
                f"💰 {data['total']} VND\n\n"
                f"👤 {data['name']}\n"
                f"📞 {data['contact']}"
            )

            keyboard = [[
                InlineKeyboardButton(
                    "✅ Подтвердить",
                    callback_data=f"confirm:{data['booking_id']}"
                )
            ]]

            await context.bot.send_message(
                chat_id=MANAGER_CHAT_ID,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

            data["status"] = "sent"
            await redis_client.set(key, json.dumps(data))


# ---------- CONFIRM ----------

async def confirm(update, context):
    query = update.callback_query
    await query.answer()

    booking_id = query.data.split(":")[1]
    key = f"booking:{booking_id}"

    data = json.loads(await redis_client.get(key))

    data["status"] = "confirmed"
    await redis_client.set(key, json.dumps(data))

    await context.bot.send_message(
        chat_id=data["client_id"],
        text="✅ Ваше бронирование подтверждено!"
    )

    await query.edit_message_text("✅ Заявка подтверждена")


# ---------- MAIN ----------

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CallbackQueryHandler(confirm, pattern="^confirm:"))

    app.job_queue.run_repeating(check_bookings, interval=5)

    app.run_polling()


if __name__ == "__main__":
    main()