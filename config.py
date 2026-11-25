import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Istanbul")

# Geçersiz saat dilimi varsa bot başlamadan hata versin.
ZoneInfo(TIMEZONE)

REPORT_HOUR = int(os.getenv("REPORT_HOUR", 23))
REPORT_MINUTE = int(os.getenv("REPORT_MINUTE", 0))

STUDY_MINUTES = 60
BREAK_MINUTES = 10
TOTAL_SESSIONS = 10

# Sabit mesai başlangıcı (Türkiye saati). Her gün otomatik başlar.
WORK_START_HOUR = 9
WORK_START_MINUTE = 0

# Faz geçişlerinin kontrol sıklığı (saniye).
TICK_SECONDS = 5

# Sabit mesajın en sık güncellenme aralığı (saniye).
REFRESH_SECONDS = 60

# Render'da kalıcı disk kullanacaksan burayı değiştir (örnek: /var/data/etut.db)
DATABASE_PATH = "etut.db"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN .env dosyasında bulunamadı!")