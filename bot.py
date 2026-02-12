import os
import json
import logging
import redis.asyncio as redis

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

redis_client = redis.from_url(REDIS_URL, decode_responses=True)


# --------- CHECK BOOKINGS ---------

async def check_bookings(context: ContextTypes.DEFAULT_TYPE):
    keys = await redis_client.keys("booking:*")

    for key in keys:
        raw = await redis_client.get(key)
        if not raw:
            continue

        data = json.loads(raw)

        if data.get("status") == "new":

            text = (
                f"🆕 Новая заявка\n\n"
                f"👤 {data['name']} (@{data.get('username')})\n"
                f"📞 {data['contact']}\n"
                f"🏨 {data['hotel']} | 🚪 {data['room']}\n\n"
                f"🛵 {data['scooter']}\n"
                f"📆 {data['days']} дней\n"
                f"💰 {data['total']} VND"
            )

            keyboard = [[
                InlineKeyboardButton(
                    "✅ Принять заявку",
                    callback_data=f"confirm:{data['booking_id']}"
                )
            ]]

            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

            data["status"] = "sent"
            await redis_client.set(key, json.dumps(data))


# --------- CONFIRM ---------

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

    manager = update.effective_user
    data["status"] = "pending"
    data["manager_username"] = manager.username

    await redis_client.set(key, json.dumps(data))

    # уведомление клиенту
    await context.bot.send_message(
        chat_id=int(data["client_id"]),
        text=(
            "✅ Заявка принята менеджером.\n\n"
            f"👨‍💼 @{manager.username}\n"
            "Скоро получите финальные детали."
        )
    )

    await query.edit_message_text("🟡 Заявка взята в работу")


# --------- MAIN ---------

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CallbackQueryHandler(confirm, pattern="^confirm:"))
    app.job_queue.run_repeating(check_bookings, interval=10, first=5)

    app.run_polling()


if __name__ == "__main__":
    main()