import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
)

# 🔥 ВСТАВЬ ТОКЕН МЕНЕДЖЕР-БОТА
TOKEN = "8430851059:AAFeU-6EGQYjQsv8DqnV0G8gwrOJdcyHjkw"

# 🔥 ID ЧАТА МЕНЕДЖЕРОВ
MANAGER_CHAT_ID = -5285917843

logging.basicConfig(level=logging.INFO)


# ---------------- РЕШЕНИЕ МЕНЕДЖЕРА ----------------

async def manager_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Проверка что нажали именно в менеджерском чате
    if query.message.chat.id != MANAGER_CHAT_ID:
        await query.answer("Недоступно", show_alert=True)
        return

    data = query.data  # approve_123456 or reject_123456
    action, user_id = data.split("_")
    user_id = int(user_id)

    if action == "approve":
        # Сообщение клиенту
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ Ваша бронь подтверждена! С вами свяжется менеджер."
        )

        # Обновляем сообщение в группе
        await query.edit_message_text(
            query.message.text + "\n\n✅ БРОНЬ ПОДТВЕРЖДЕНА"
        )

    elif action == "reject":
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ К сожалению, в бронировании отказано."
        )

        await query.edit_message_text(
            query.message.text + "\n\n❌ БРОНЬ ОТКЛОНЕНА"
        )


# ---------------- MAIN ----------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Ловим кнопки approve_/reject_
    app.add_handler(
        CallbackQueryHandler(manager_decision, pattern="^(approve|reject)_")
    )

    app.run_polling()


if __name__ == "__main__":
    main()