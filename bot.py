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
REDIS_URL = os.getenv("REDIS_URL")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

(
    CONFIG,
    DEPOSIT,
    FINAL,
    PAYMENT
) = range(4)


# ================= КОНФИГУРАЦИЯ =================

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


# ================= ПРОВЕРКА НОВЫХ ЗАЯВОК =================

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
                f"🛵 {data['scooter']}\n"
                f"📆 {data['days']} дней\n"
                f"💵 {data['total']} VND\n\n"
                f"👤 {data['name']}\n"
                f"🏨 {data['hotel']} | {data['room']}\n"
                f"📞 {data['contact']}\n"
                f"📊 {data['risk_level']}"
            )

            keyboard = [[
                InlineKeyboardButton(
                    "🟡 Принять заявку",
                    callback_data=f"accept:{data['booking_id']}"
                )
            ]]

            msg = await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            data["status"] = "sent"
            data["group_message_id"] = msg.message_id

            await redis_client.set(key, json.dumps(data))


# ================= ПРИНЯТИЕ =================

async def accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    booking_id = query.data.split(":")[1]
    key = f"booking:{booking_id}"

    raw = await redis_client.get(key)
    if not raw:
        return ConversationHandler.END

    data = json.loads(raw)

    data["status"] = "in_progress"
    data["manager_username"] = update.effective_user.username

    await redis_client.set(key, json.dumps(data))

    context.user_data["booking_id"] = booking_id
    context.user_data["config_step"] = 0
    context.user_data["equipment"] = {}

    await send_config_step(query, context)
    return CONFIG


# ================= ШАГ КОНФИГА =================

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


# ================= ОБРАБОТКА КНОПОК =================

async def handle_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    step = context.user_data["config_step"]
    key_name, _, _ = CONFIG_FLOW[step]
    value = query.data.split(":")[1]

    # сохраняем ВСЕ положительные значения
    if value not in ["Нет", "Неполный", "Грязный"]:
        context.user_data["equipment"][key_name] = value

    context.user_data["config_step"] += 1

    if context.user_data["config_step"] >= len(CONFIG_FLOW):
        await query.edit_message_text("💰 Введите депозит (можно в любом формате):")
        return DEPOSIT

    await send_config_step(query, context)
    return CONFIG


# ================= ДЕПОЗИТ =================

async def deposit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    deposit = update.message.text.strip()

    booking_id = context.user_data["booking_id"]
    key = f"booking:{booking_id}"

    raw = await redis_client.get(key)
    data = json.loads(raw)

    data["equipment"] = context.user_data["equipment"]
    data["deposit"] = deposit

    await redis_client.set(key, json.dumps(data))

    equipment_text = "\n".join(data["equipment"].values())

    keyboard = [[InlineKeyboardButton("✅ Подтвердить", callback_data="final")]]

    await update.message.reply_text(
        f"📋 Проверка заявки\n\n"
        f"{equipment_text}\n\n"
        f"💰 Депозит: {deposit}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return FINAL


# ================= ПОДТВЕРЖДЕНИЕ =================

async def final_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    booking_id = context.user_data["booking_id"]
    key = f"booking:{booking_id}"

    raw = await redis_client.get(key)
    data = json.loads(raw)

    keyboard = [[
        InlineKeyboardButton("💵 Оплата принята", callback_data="paid")
    ]]

    await query.edit_message_text(
        f"Пожалуйста примите:\n\n"
        f"💰 Депозит: {data['deposit']}\n"
        f"💵 Оплата аренды: {data['total']} VND",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return PAYMENT


# ================= ОПЛАТА =================

async def payment_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    booking_id = context.user_data["booking_id"]
    key = f"booking:{booking_id}"

    raw = await redis_client.get(key)
    data = json.loads(raw)

    data["status"] = "confirmed"
    await redis_client.set(key, json.dumps(data))

    equipment_text = "\n".join(data["equipment"].values())

    full_text = (
        "✅ Оплата подтверждена. Заявка завершена.\n\n"
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

    # обновляем сообщение в группе
    await context.bot.edit_message_text(
        chat_id=GROUP_CHAT_ID,
        message_id=data["group_message_id"],
        text=full_text
    )

    # ====== ОТПРАВЛЯЕМ СОБЫТИЕ В REDIS ДЛЯ КЛИЕНТСКОГО БОТА ======

    await redis_client.set(
        f"client_event:{booking_id}",
        json.dumps({
            "type": "booking_confirmed",
            "booking_id": booking_id
        })
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
    app.job_queue.run_repeating(check_bookings, interval=10, first=5)

    app.run_polling()


if __name__ == "__main__":
    main()