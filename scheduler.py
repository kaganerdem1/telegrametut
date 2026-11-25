import logging
from datetime import datetime, timedelta
from math import ceil
from zoneinfo import ZoneInfo

from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

import config
import database
from keyboards import join_keyboard

logger = logging.getLogger(__name__)

TZ = ZoneInfo(config.TIMEZONE)
PHASE_LABEL = {"study": "📚 Çalışma", "break": "☕ Mola"}

_last_refresh = {}


def now():
    return datetime.now(TZ)


def today_str():
    return now().date().isoformat()


def parse_time(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt


def iso(dt):
    return dt.isoformat()


def phase_minutes(phase):
    return config.STUDY_MINUTES if phase == "study" else config.BREAK_MINUTES


def get_active_timer(chat_id):
    timer = database.get_timer(f"group_{chat_id}")
    return timer if timer and timer["active"] else None


def progress_bar(ratio, width=12):
    filled = round(ratio * width)
    return "█" * filled + "░" * (width - filled)


def participant_ids_and_names(timer_id):
    result = []
    for row in database.get_participants(timer_id):
        user = database.get_user(row["user_id"])
        name = user["first_name"] if user and user["first_name"] else "Öğrenci"
        result.append((row["user_id"], name))
    return result


def timer_text(timer):
    start = parse_time(timer["start_time"])
    end = parse_time(timer["end_time"])
    current = now()

    total = max(1.0, (end - start).total_seconds())
    elapsed = (current - start).total_seconds()
    ratio = min(1.0, max(0.0, elapsed / total))

    remaining_min = max(0, ceil((end - current).total_seconds() / 60))
    participants = participant_ids_and_names(timer["timer_id"])
    joined = "\n".join(f"✅ {name}" for _, name in participants) \
        if participants else "henüz yok"

    return (
        f"📚 ORTAK ETÜT  ·  {timer['session_number']}/{config.TOTAL_SESSIONS}\n\n"
        f"{PHASE_LABEL[timer['phase']]}\n"
        f"{progress_bar(ratio)}  %{round(ratio * 100)}\n\n"
        f"⏱ Kalan: {remaining_min} dk\n"
        f"👥 Katılan ({len(participants)}):\n{joined}\n\n"
        "🙋 Katılmak için butona bas."
    )


async def refresh(bot, timer, force=False):
    if not timer or not timer["message_id"]:
        return

    timer_id = timer["timer_id"]
    last = _last_refresh.get(timer_id)
    current = now()

    if not force and last and (current - last).total_seconds() < config.REFRESH_SECONDS:
        return

    _last_refresh[timer_id] = current
    participant_count = len(database.get_participants(timer_id))

    try:
        await bot.edit_message_text(
            chat_id=timer["chat_id"],
            message_id=timer["message_id"],
            text=timer_text(timer),
            reply_markup=join_keyboard(participant_count),
        )
    except BadRequest as error:
        if "not modified" not in str(error).lower():
            logger.warning("Zamanlayıcı mesajı güncellenemedi: %s", error)
    except TelegramError as error:
        logger.warning("Zamanlayıcı mesajı güncellenemedi: %s", error)


async def move_to_bottom(bot, chat_id):
    """Yeni mesaj atmak yerine, var olan sabit mesajı anında günceller."""
    timer = get_active_timer(chat_id)
    if not timer or not timer["message_id"]:
        return

    participant_count = len(database.get_participants(timer["timer_id"]))

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=timer["message_id"],
            text=timer_text(timer),
            reply_markup=join_keyboard(participant_count),
        )
        _last_refresh[timer["timer_id"]] = now()
    except BadRequest as error:
        if "not modified" not in str(error).lower():
            logger.warning("Mevcut mesaj güncellenemedi, yenisini gönderiyorum: %s", error)
            try:
                new_message = await bot.send_message(
                    chat_id=chat_id,
                    text=timer_text(timer),
                    reply_markup=join_keyboard(participant_count),
                )
                database.set_timer_message(timer["timer_id"], new_message.message_id)
                _last_refresh[timer["timer_id"]] = now()
            except TelegramError as e:
                logger.warning("Yeni zamanlayıcı mesajı da gönderilemedi: %s", e)
    except TelegramError as error:
        logger.warning("Zamanlayıcı mesajı güncellenemedi: %s", error)


def record_phase(timer, phase, start, end, finished):
    for participant in database.get_participants(timer["timer_id"]):
        joined = parse_time(participant["joined_at"])
        effective_start = max(start, joined)
        minutes = int((end - effective_start).total_seconds() // 60)

        if minutes <= 0:
            continue

        full = finished and joined <= start
        database.add_activity(
            user_id=participant["user_id"],
            chat_id=timer["chat_id"],
            activity_type=phase,
            start_time=iso(effective_start),
            end_time=iso(end),
            duration=minutes,
            completed=1 if (full and phase == "study") else 0,
        )


async def _finish(bot, timer):
    _last_refresh.pop(timer["timer_id"], None)
    chat_id = timer["chat_id"]

    try:
        await bot.send_message(
            chat_id=chat_id,
            text="🛑 ORTAK ETÜT SONA ERDİ\n\nGünün sonunda raporlar paylaşılacak.",
        )
    except TelegramError as error:
        logger.warning("Bitiş mesajı gönderilemedi: %s", error)

    if timer["message_id"]:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=timer["message_id"])
        except TelegramError as error:
            logger.warning("Zamanlayıcı mesajı silinemedi: %s", error)


async def _announce_phase(bot, chat_id, session_number, phase):
    if phase == "study":
        text = (
            f"📚 {session_number}. ETÜT BAŞLADI!\n"
            f"⏱ {config.STUDY_MINUTES} dakika boyunca odaklan."
        )
    else:
        text = (
            f"☕ {session_number}. etüt tamamlandı.\n"
            f"⏱ {config.BREAK_MINUTES} dakika mola başladı."
        )
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except TelegramError as error:
        logger.warning("Faz bildirimi gönderilemedi: %s", error)


async def _process(bot, timer_id):
    changed = False

    while True:
        timer = database.get_timer(timer_id)
        if not timer or not timer["active"]:
            return

        end = parse_time(timer["end_time"])
        if end > now():
            break

        phase = timer["phase"]
        session = timer["session_number"]
        start = parse_time(timer["start_time"])

        record_phase(timer, phase, start, end, finished=True)

        if phase == "study" and session >= config.TOTAL_SESSIONS:
            database.stop_timer(timer_id)
            await bot.send_message(
                chat_id=timer["chat_id"],
                text=f"🏆 {config.TOTAL_SESSIONS} etüdün tamamlandı! "
                     "Harika bir çalışma gerçekleştirdiniz.",
            )
            await _finish(bot, timer)
            return

        if phase == "study":
            new_phase, new_session = "break", session
        else:
            new_phase, new_session = "study", session + 1

        database.update_timer(
            timer_id,
            new_phase,
            new_session,
            iso(end),
            iso(end + timedelta(minutes=phase_minutes(new_phase))),
        )
        changed = True

    if changed:
        timer = database.get_timer(timer_id)
        await _announce_phase(
            bot, timer["chat_id"],
            timer["session_number"], timer["phase"],
        )
        await move_to_bottom(bot, timer["chat_id"])


async def tick(context: ContextTypes.DEFAULT_TYPE):
    for timer in database.get_active_timers():
        timer_id = timer["timer_id"]
        try:
            await _process(context.bot, timer_id)
            current = database.get_timer(timer_id)
            if current and current["active"]:
                await refresh(context.bot, current)
        except Exception:
            logger.exception("Zamanlayıcı işlenirken hata: %s", timer_id)


async def start_timer(bot, chat_id, starter_id):
    timer_id = f"group_{chat_id}"
    start = now()
    end = start + timedelta(minutes=config.STUDY_MINUTES)

    database.create_timer(
        timer_id, chat_id, "study", 1, iso(start), iso(end)
    )
    database.add_participant(timer_id, starter_id, iso(start))

    timer = database.get_timer(timer_id)
    participant_count = len(database.get_participants(timer_id))

    await _announce_phase(bot, chat_id, 1, "study")

    message = await bot.send_message(
        chat_id=chat_id,
        text=timer_text(timer),
        reply_markup=join_keyboard(participant_count),
    )
    database.set_timer_message(timer_id, message.message_id)
    _last_refresh[timer_id] = now()


async def start_fixed_shift(bot, chat_id):
    timer_id = f"group_{chat_id}"
    existing = database.get_timer(timer_id)
    if existing and existing["active"]:
        return

    start = now()
    end = start + timedelta(minutes=config.STUDY_MINUTES)

    database.create_timer(
        timer_id, chat_id, "study", 1, iso(start), iso(end)
    )
    timer = database.get_timer(timer_id)

    await _announce_phase(bot, chat_id, 1, "study")

    message = await bot.send_message(
        chat_id=chat_id,
        text=timer_text(timer),
        reply_markup=join_keyboard(0),
    )
    database.set_timer_message(timer_id, message.message_id)
    _last_refresh[timer_id] = now()


async def stop_timer(bot, timer_id):
    await _process(bot, timer_id)

    timer = database.get_timer(timer_id)
    if not timer or not timer["active"]:
        return

    start = parse_time(timer["start_time"])
    current = now()
    if current > start:
        record_phase(timer, timer["phase"], start, current, finished=False)

    database.stop_timer(timer_id)
    await _finish(bot, timer)