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

TOKEN = os.getenv("8430851059:AAFeU-6EGQYjQsv8DqnV0G8gwrOJdcyHjkw")
TECH_GROUP_ID = int(os.getenv("-1003726782924"))
MANAGER_GROUP_ID = int(os.getenv("-5285917843"))

logging.basicConfig(level=logging.INFO)

# Хранилище заявок в памяти
active_bookings = {}
booking_extras = {}
booking_managers = {}
booking_deposit_mode = {}


# ===============================
# Приём заявки из тех. группы
# ===============================
async def receive_from_tech(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != TECH_GROUP_ID:
        return

    text = update.message.text

    if not text.startswith("NEW_BOOKING"):
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

    message_text = f"""
🆕 Новая заявка

👤 Имя: {data.get('name')}
🏍 Модель: {data.get('model')}
📅 Дней: {data.get('days')}
💰 Итого: {data.get('total')}

📞 Контакт:
{data.get('contact')}

🆔 Booking ID: {booking_id}
"""

    await context.bot.send_message(
        chat_id=MANAGER_GROUP_ID,
        text=message_text,
        reply_markup=keyboard
    )


# ===============================
# Менеджер нажал "Взять"
# ===============================
async def take_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    booking_id = query.data.replace("take_", "")

    if booking_id not in active_bookings:
        await query.edit_message_text("⚠ Заявка не найдена или устарела")
        return

    # Защита от повторного взятия
    if booking_id in booking_managers:
        await query.answer("Заявка уже взята другим менеджером", show_alert=True)
        return

    manager_name = query.from_user.full_name
    booking_managers[booking_id] = manager_name

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1 шлем", callback_data=f"extra_helmet1_{booking_id}")],
        [InlineKeyboardButton("2 шлема", callback_data=f"extra_helmet2_{booking_id}")],
        [InlineKeyboardButton("Полный бак", callback_data=f"extra_fulltank_{booking_id}")],
        [InlineKeyboardButton("Чистый байк", callback_data=f"extra_clean_{booking_id}")],
        [InlineKeyboardButton("💰 Ввести депозит", callback_data=f"deposit_{booking_id}")],
        [InlineKeyboardButton("✅ Подтвердить бронирование", callback_data=f"confirm_{booking_id}")]
    ])

    await query.edit_message_text(
        text=f"🔧 Работа с заявкой {booking_id}\n👤 Менеджер: {manager_name}\n\nВыберите комплектацию:",
        reply_markup=keyboard
    )


# ===============================
# Выбор комплектации
# ===============================
async def handle_extras(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    action = parts[1]
    booking_id = parts[2]

    if booking_id not in booking_extras:
        return

    extra_map = {
        "helmet1": "1 шлем",
        "helmet2": "2 шлема",
        "fulltank": "Полный бак",
        "clean": "Чистый байк"
    }

    extra_text = extra_map.get(action)

    if extra_text and extra_text not in booking_extras[booking_id]:
        booking_extras[booking_id].append(extra_text)

    extras_text = "\n".join(booking_extras[booking_id]) or "Нет"

    await query.edit_message_text(
        text=f"🔧 Работа с заявкой {booking_id}\n"
             f"👤 Менеджер: {booking_managers[booking_id]}\n\n"
             f"📦 Выбрана комплектация:\n{extras_text}\n\n"
             f"Продолжайте выбор или подтвердите.",
        reply_markup=query.message.reply_markup
    )


# ===============================
# Режим ввода депозита
# ===============================
async def deposit_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    booking_id = query.data.replace("deposit_", "")
    booking_deposit_mode[booking_id] = True

    await query.edit_message_text(
        f"💰 Введите сумму депозита для заявки {booking_id}:"
    )


async def receive_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    for booking_id in booking_deposit_mode:
        if booking_deposit_mode[booking_id]:
            booking_extras[booking_id].append(f"Депозит: {text}")
            booking_deposit_mode[booking_id] = False

            await update.message.reply_text("✅ Депозит сохранён")
            return


# ===============================
# Подтверждение бронирования
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

    # Можно удалить из активных
    active_bookings.pop(booking_id, None)


# ===============================
# Запуск бота
# ===============================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_from_tech))
    app.add_handler(CallbackQueryHandler(take_booking, pattern="^take_"))
    app.add_handler(CallbackQueryHandler(handle_extras, pattern="^extra_"))
    app.add_handler(CallbackQueryHandler(deposit_request, pattern="^deposit_"))
    app.add_handler(CallbackQueryHandler(confirm_booking, pattern="^confirm_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_deposit))

    print("Manager bot started...")
    app.run_polling()