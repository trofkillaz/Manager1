import os
import json
import logging
import redis.asyncio as redis

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_1 = os.getenv("REDIS_1")
REDIS_2 = os.getenv("REDIS_2")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

redis_booking = redis.from_url(REDIS_1, decode_responses=True)
redis_event = redis.from_url(REDIS_2, decode_responses=True)

(
    CONFIG,
    DEPOSIT,
    FINAL,
    PAYMENT
) = range(4)

# ================= КОНФИГ =================

CONFIG_FLOW = [
    ("helmet", "Шлем", ["1 шлем", "2 шлема"]),
    ("raincoat", "Плащи / дождевики", ["2 плаща", "2 дождевика"]),
    ("glasses", "Очки", ["Да", "Нет"]),
    ("napkin", "Салфетка", ["Да", "Нет"]),
    ("tank", "Бак", ["Полный", "Неполный"]),
    ("clean", "Состояние", ["Чистый", "Грязный"]),
    ("box", "Багажник", ["Да", "Нет"]),
    ("pillow", "Подушка", ["Да", "Нет"]),
]

# ================= ПРОВЕРКА НОВЫХ =================

async def check_bookings(context: ContextTypes.DEFAULT_TYPE):
    async for key in redis_booking.scan_iter("booking:*"):
        raw = await redis_booking.get(key)
        if not raw:
            continue

        data = json.loads(raw)

        if data.get("status") != "new":
            continue

        text = (
            f"🆕 Новая заявка\n\n"
            f"🛵 {data['scooter']}\n"
            f"📆 {data['days']} дней\n"
            f"💵 {data['total']} VND\n\n"
            f"👤 {data['name']}\n"
            f"🏨 {data['hotel']} | {data['room']}\n"
            f"📞 {data['contact']}\n"
            f"📊 {data['risk_level']}"
        )

        keyboard = [[
            InlineKeyboardButton("🟢 Принять", callback_data=f"accept:{data['booking_id']}"),
            InlineKeyboardButton("🔴 Отказать", callback_data=f"reject:{data['booking_id']}")
        ]]

        msg = await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        data["status"] = "sent"
        data["group_message_id"] = msg.message_id

        await redis_booking.set(key, json.dumps(data), ex=60 * 60 * 24)

# ================= ОТКАЗ =================

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    booking_id = query.data.split(":")[1]
    key = f"booking:{booking_id}"

    raw = await redis_booking.get(key)
    if not raw:
        return

    data = json.loads(raw)
    data["status"] = "rejected"

    await redis_booking.set(key, json.dumps(data), ex=60 * 60 * 24)

    await context.bot.edit_message_text(
        chat_id=GROUP_CHAT_ID,
        message_id=data["group_message_id"],
        text="❌ Заявка отклонена"
    )

    await redis_event.set(
        f"event:{booking_id}",
        json.dumps({
            "type": "booking_update",
            "booking_id": booking_id,
            "status": "rejected"
        }),
        ex=60 * 60 * 24
    )

# ================= ПРИНЯТИЕ =================

async def accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    booking_id = query.data.split(":")[1]
    key = f"booking:{booking_id}"

    raw = await redis_booking.get(key)
    if not raw:
        return ConversationHandler.END

    data = json.loads(raw)

    if data.get("status") != "sent":
        return ConversationHandler.END

    data["status"] = "in_progress"
    data["manager_username"] = update.effective_user.username or "manager"

    await redis_booking.set(key, json.dumps(data), ex=60 * 60 * 24)

    context.user_data.clear()
    context.user_data["booking_id"] = booking_id
    context.user_data["config_step"] = 0
    context.user_data["equipment"] = {}

    await send_config_step(query, context)
    return CONFIG

# ================= КОНФИГ ШАГ =================

async def send_config_step(query, context):
    step = context.user_data["config_step"]
    key_name, title, options = CONFIG_FLOW[step]

    keyboard = [[
        InlineKeyboardButton(options[0], callback_data=f"cfg:{options[0]}"),
        InlineKeyboardButton(options[1], callback_data=f"cfg:{options[1]}")
    ]]

    await query.edit_message_text(
        f"🔧 {title}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= ОБРАБОТКА =================

async def handle_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    step = context.user_data["config_step"]
    key_name, title, _ = CONFIG_FLOW[step]
    value = query.data.split(":")[1]

    if value not in ["Нет", "Неполный", "Грязный"]:
        context.user_data["equipment"][title] = value

    context.user_data["config_step"] += 1

    if context.user_data["config_step"] >= len(CONFIG_FLOW):
        await query.edit_message_text("💰 Введите депозит:")
        return DEPOSIT

    await send_config_step(query, context)
    return CONFIG

# ================= ДЕПОЗИТ =================

async def deposit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    deposit = update.message.text.strip()

    booking_id = context.user_data["booking_id"]
    key = f"booking:{booking_id}"

    raw = await redis_booking.get(key)
    data = json.loads(raw)

    data["equipment"] = context.user_data["equipment"]
    data["deposit"] = deposit

    await redis_booking.set(key, json.dumps(data), ex=60 * 60 * 24)

    equipment_text = "\n".join(
        [f"• {v}" for v in data["equipment"].values()]
    )

    keyboard = [[InlineKeyboardButton("✅ Подтвердить", callback_data="final")]]

    await update.message.reply_text(
        f"📋 Проверка\n\n{equipment_text}\n\n💰 Депозит: {deposit}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return FINAL

# ================= ФИНАЛ =================

async def final_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    booking_id = context.user_data["booking_id"]
    key = f"booking:{booking_id}"

    raw = await redis_booking.get(key)
    data = json.loads(raw)

    keyboard = [[
        InlineKeyboardButton("💵 Оплата получена", callback_data="paid")
    ]]

    await query.edit_message_text(
        f"Примите оплату:\n\n"
        f"💰 Депозит: {data['deposit']}\n"
        f"💵 Аренда: {data['total']} VND",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return PAYMENT

# ================= ОПЛАТА =================

async def payment_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    booking_id = context.user_data["booking_id"]
    key = f"booking:{booking_id}"

    raw = await redis_booking.get(key)
    data = json.loads(raw)

    data["status"] = "confirmed"

    await redis_booking.set(key, json.dumps(data), ex=60 * 60 * 24)

    equipment_text = "\n".join(
        [f"• {v}" for v in data.get("equipment", {}).values()]
    )

    full_text = (
        "✅ Заявка завершена\n\n"
        f"🛵 {data['scooter']}\n"
        f"📆 {data['days']} дней\n"
        f"💵 {data['total']} VND\n"
        f"💰 Депозит: {data['deposit']}\n\n"
        f"{equipment_text}\n\n"
        f"👤 {data['name']}\n"
        f"🏨 {data['hotel']} | {data['room']}\n"
        f"📞 {data['contact']}\n\n"
        f"👨‍💼 @{data['manager_username']}"
    )

    await context.bot.edit_message_text(
        chat_id=GROUP_CHAT_ID,
        message_id=data["group_message_id"],
        text=full_text
    )

    await redis_event.set(
        f"event:{booking_id}",
        json.dumps({
            "type": "booking_update",
            "booking_id": booking_id,
            "status": "approved",
            "deposit": data["deposit"],
            "final_total": data["total"],
            "manager": f"@{data['manager_username']}"
        }),
        ex=60 * 60 * 24
    )

    return ConversationHandler.END

# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(accept, pattern="^accept:")],
        states={
            CONFIG: [CallbackQueryHandler(handle_config, pattern="^cfg:")],
            DEPOSIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_input)],
            FINAL: [CallbackQueryHandler(final_confirm, pattern="^final$")],
            PAYMENT: [CallbackQueryHandler(payment_confirm, pattern="^paid$")],
        },
        fallbacks=[],
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(reject, pattern="^reject:"))

    app.job_queue.run_repeating(check_bookings, interval=8, first=5)

    app.run_polling()

if __name__ == "__main__":
    main()