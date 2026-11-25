import logging
from datetime import time as dtime
from zoneinfo import ZoneInfo

from telegram import BotCommand
from telegram.ext import Application

import config
import database
import scheduler
import reports
import handlers

# Loglama ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


async def start_fixed_shifts(context):
    """Her gün 09:00'da tüm kayıtlı gruplarda sabit mesaiyi başlatır."""
    for group in database.get_groups():
        chat_id = group["chat_id"]
        try:
            await scheduler.start_fixed_shift(context.bot, chat_id)
        except Exception:
            logger.exception("Sabit mesai başlatılamadı: %s", chat_id)


async def post_init(application):
    """Bot başlarken veritabanını kurar ve zamanlayıcıları (job) ayarlar."""
    database.init_db()

    # Bot komutlarını Telegram'a tanıt
    await application.bot.set_my_commands([
        BotCommand("start", "Ortak etüdü hemen başlat"),
        BotCommand("stop", "Ortak etüdü bitir (yönetici)"),
    ])

    # Her 5 saniyede bir çalışıp süreleri kontrol eden döngü
    application.job_queue.run_repeating(
        scheduler.tick,
        interval=config.TICK_SECONDS,
        first=5,
        name="tick",
    )

    # Her sabah 09:00'da otomatik başlayan sabit mesai
    tz = ZoneInfo(config.TIMEZONE)
    application.job_queue.run_daily(
        start_fixed_shifts,
        time=dtime(
            hour=config.WORK_START_HOUR,
            minute=config.WORK_START_MINUTE,
            tzinfo=tz,
        ),
        name="fixed_shift",
    )

    # Günlük raporları gönderme zamanlayıcısı
    reports.schedule_daily_reports(application)

    logger.info("Etüt Odası Botu hazır!")


async def error_handler(update, context):
    """Botta oluşan hataları yakalar ve loglar."""
    logger.error("Hata oluştu", exc_info=context.error)


def main():
    """Botu başlatan ana fonksiyon."""
    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Komutları ve mesaj dinleyicilerini ekle
    handlers.register_handlers(application)
    application.add_error_handler(error_handler)

    logger.info("Bot başlatılıyor...")

    # Botu çalıştır (mesajları ve buton tıklamalarını dinle)
    application.run_polling(
        allowed_updates=["message", "callback_query"]
    )


if __name__ == "__main__":
    main()