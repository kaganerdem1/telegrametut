import logging
from datetime import time
from zoneinfo import ZoneInfo

from telegram.error import TelegramError
from telegram.ext import ContextTypes

import config
import database
import scheduler

logger = logging.getLogger(__name__)

MEDALS = ["🥇", "🥈", "🥉"]


def format_duration(minutes):
    hours, mins = divmod(int(minutes or 0), 60)
    return f"{hours} saat {mins} dakika"


async def send_daily_reports(context: ContextTypes.DEFAULT_TYPE):
    day = scheduler.today_str()

    for user in database.get_all_users():
        user_id = user["user_id"]

        if database.report_was_sent(user_id, day):
            continue

        stats = database.get_daily_stats(user_id, day)
        study = stats["study"] or 0
        breaks = stats["breaks"] or 0
        sessions = stats["sessions"] or 0

        if study == 0 and breaks == 0:
            database.mark_report_sent(user_id, day)
            continue

        text = (
            "🌙 GÜNLÜK ÇALIŞMA RAPORUN\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"📅 Tarih: {day}\n\n"
            f"📚 Bugün çalıştığın süre: {format_duration(study)}\n"
            f"☕ Toplam mola: {format_duration(breaks)}\n"
            f"🏆 Tamamlanan etüt: {sessions}\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Yarın yeni hedeflere ulaşmak üzere. 💪"
        )

        try:
            await context.bot.send_message(chat_id=user_id, text=text)
            database.mark_report_sent(user_id, day)
        except TelegramError as error:
            logger.warning("Özel rapor gönderilemedi: %s - %s", user_id, error)

    for group in database.get_groups():
        chat_id = group["chat_id"]

        if database.report_was_sent(chat_id, day):
            continue

        rows = database.get_group_leaderboard(chat_id, day)
        if not rows:
            database.mark_report_sent(chat_id, day)
            continue

        lines = [f"🏆 GÜNLÜK SIRALAMA ({day})\n"]
        for index, row in enumerate(rows):
            medal = MEDALS[index] if index < 3 else "🔹"
            lines.append(
                f"{medal} {row['first_name']} - "
                f"{format_duration(row['total'])}"
            )

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
            )
            database.mark_report_sent(chat_id, day)
        except TelegramError as error:
            logger.warning("Grup raporu gönderilemedi: %s - %s", chat_id, error)


def schedule_daily_reports(application):
    from datetime import time as dtime
    tz = ZoneInfo(config.TIMEZONE)
    report_time = dtime(
        hour=config.REPORT_HOUR,
        minute=config.REPORT_MINUTE,
        tzinfo=tz,
    )
    application.job_queue.run_daily(
        send_daily_reports,
        time=report_time,
        name="daily_reports",
    )