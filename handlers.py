import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import database
import scheduler

logger = logging.getLogger(__name__)

GROUP_TYPES = ("group", "supergroup")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    database.register_user(user)

    if chat.type == "private":
        database.activate_private(user.id)
        await update.message.reply_text(
            f"Merhaba {user.first_name}! 📚\n\n"
            "Etüt Odası Botuna hoş geldin.\n"
            "Her gün 09:00'da otomatik başlayan 10 etütlük mesai var.\n"
            "İstersen /start ile hemen de başlatabilirsin.\n"
            "Günün sonunda çalışma raporunu buradan alacaksın."
        )
        return

    if chat.type not in GROUP_TYPES:
        return

    database.register_group(chat.id, chat.title)

    if scheduler.get_active_timer(chat.id):
        await update.message.reply_text(
            "⚠️ Bu grupta zaten devam eden bir etüt var.\n"
            "Katılmak için 🙋 Katıl butonuna bas."
        )
        return

    # Manuel başlatma: saat 09:00'ı beklemeden hemen başlar.
    await scheduler.start_timer(context.bot, chat.id, user.id)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in GROUP_TYPES:
        await update.message.reply_text(
            "Etüt grupta, grup yöneticisi tarafından /stop ile bitirilir."
        )
        return

    timer = scheduler.get_active_timer(chat.id)
    if not timer:
        await update.message.reply_text("Aktif etüt bulunmuyor.")
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
    except TelegramError as error:
        logger.exception("Yönetici kontrolü yapılamadı: %s", error)
        await update.message.reply_text(
            "Yönetici kontrolü yapılamadı. Bot grupta yönetici mi?"
        )
        return

    if member.status not in ("administrator", "creator"):
        await update.message.reply_text(
            "Ortak etüdü yalnızca grup yöneticileri bitirebilir."
        )
        return

    try:
        await scheduler.stop_timer(context.bot, timer["timer_id"])
    except Exception as error:
        logger.exception("Etüt durdurulurken hata: %s", error)
        await update.message.reply_text(
            f"Etüt durdurulurken hata oluştu: {error}"
        )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data != "join":
        await query.answer()
        return

    timer = scheduler.get_active_timer(query.message.chat.id)
    if not timer:
        await query.answer("Aktif ortak etüt yok.", show_alert=True)
        return

    user = query.from_user
    database.register_user(user)

    already_joined = any(
        row["user_id"] == user.id
        for row in database.get_participants(timer["timer_id"])
    )
    if already_joined:
        await query.answer("✅ Zaten bu etüte katıldın!", show_alert=True)
        return

    database.add_participant(
        timer["timer_id"],
        user.id,
        scheduler.iso(scheduler.now()),
    )

    # Listeyi ve butonun yanındaki sayacı hemen güncelle.
    await scheduler.refresh(context.bot, timer, force=True)
    await query.answer(f"✅ Katıldın, {query.from_user.first_name}!")


async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grupta yeni bir mesaj gelince zamanlayıcıyı en alta taşır."""
    chat = update.effective_chat
    if chat.type not in GROUP_TYPES:
        return
    await scheduler.move_to_bottom(context.bot, chat.id)


def register_handlers(application):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, on_group_message)
    )