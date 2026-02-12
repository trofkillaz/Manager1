import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ===== Переменные из Railway =====
TOKEN = os.getenv("BOT_TOKEN")
TECH_GROUP_ID = int(os.getenv("TECH_GROUP_ID"))
MANAGER_GROUP_ID = int(os.getenv("MANAGER_GROUP_ID"))

logging.basicConfig(level=logging.INFO)

active_bookings = {}
booking_extras = {}
booking_managers = {}

# ===============================
# Приём заявки из TECH группы
# ===============================
async def receive_from_tech(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != TECH_GROUP_ID:
        return

    text = update.message.text
    if not text or not text.startswith("NEW_BOOKING"):
        return

    lines = text.split("\n")

    data = {}
    for line in lines[1:]:
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()

    booking_id = data.get("booking_id")
    if not booking_id:
        return

    active_bookings[booking_id] = data
    booking_extras[booking_id] = []

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Взять заявку", callback_data=f"take_{booking_id}")]
    ])

    message_text = (
        f"🆕 Новая заявка\n\n"
        f"👤 Имя: {data.get('name')}\n"
        f"🏍 Модель: {data.get('model')}\n"
        f"📅 Дней: {data.get('days')}\n"
        f"💰 Итого: {data.get('total')}\n\n"
        f"📞 Контакт:\n{data.get('contact')}\n\n"
        f"🆔 Booking ID: {booking_id}"
    )

    await context.bot.send_message(
        chat_id=MANAGER_GROUP_ID,
        text=message_text,
        reply_markup=keyboard
    )


# ===============================
# Взять заявку
# ===============================
async def take_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    booking_id = query.data.replace("take_", "")

    if booking_id in booking_managers:
        await query.answer("⚠ Уже взята", show_alert=True)
        return

    manager_name = query.from_user.full_name
    booking_managers[booking_id] = manager_name

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1 шлем", callback_data=f"extra_helmet1_{booking_id}")],
        [InlineKeyboardButton("2 шлема", callback_data=f"extra_helmet2_{booking_id}")],
        [InlineKeyboardButton("Полный бак", callback_data=f"extra_fulltank_{booking_id}")],
        [InlineKeyboardButton("Чистый байк", callback_data=f"extra_clean_{booking_id}")],
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{booking_id}")]
    ])

    await query.edit_message_text(
        f"🔧 Работа с заявкой {booking_id}\n"
        f"👤 Менеджер: {manager_name}\n\n"
        f"Выберите комплектацию:",
        reply_markup=keyboard
    )


# ===============================
# Комплектация
# ===============================
async def handle_extras(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    action = parts[1]
    booking_id = parts[2]

    extra_map = {
        "helmet1": "1 шлем",
        "helmet2": "2 шлема",
        "fulltank": "Полный бак",
        "clean": "Чистый байк"
    }

    extra_text = extra_map.get(action)

    if extra_text and extra_text not in booking_extras.get(booking_id, []):
        booking_extras[booking_id].append(extra_text)

    extras = "\n".join(booking_extras.get(booking_id, [])) or "Нет"

    await query.edit_message_text(
        f"🔧 Работа с заявкой {booking_id}\n"
        f"👤 Менеджер: {booking_managers.get(booking_id)}\n\n"
        f"📦 Комплектация:\n{extras}",
        reply_markup=query.message.reply_markup
    )


# ===============================
# Подтверждение
# ===============================
async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    booking_id = query.data.replace("confirm_", "")

    extras = "\n".join(booking_extras.get(booking_id, [])) or "Нет"

    await query.edit_message_text(
        f"✅ Заявка {booking_id} подтверждена\n\n"
        f"👤 Менеджер: {booking_managers.get(booking_id)}\n\n"
        f"📦 Комплектация:\n{extras}"
    )


# ===============================
# Ответ в личке / других чатах
# ===============================
async def reply_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id == TECH_GROUP_ID:
        return

    await update.message.reply_text(
        "🤖 Я не тот бот, который тебе нужен.\n"
        "Этот бот работает только для обработки заявок."
    )


# ===============================
# Запуск
# ===============================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_from_tech))
    app.add_handler(CallbackQueryHandler(take_booking, pattern="^take_"))
    app.add_handler(CallbackQueryHandler(handle_extras, pattern="^extra_"))
    app.add_handler(CallbackQueryHandler(confirm_booking, pattern="^confirm_"))

    # добавляем последним
    app.add_handler(MessageHandler(filters.TEXT, reply_any_message))

    print("Manager bot started...")
    app.run_polling()