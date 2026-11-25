import os
import threading
import time
import staypresent
from bot import main as run_bot

def start_web_server():
    """
    Render'ın uygulamayı uyutmaması için sahte bir web sunucusu başlatır.
    Bu sunucu arka planda (ayrı bir thread'de) çalışır.
    """
    # Botun başlaması için çok kısa bir süre bekle
    time.sleep(2)
    
    port = int(os.getenv("PORT", 8080))
    print(f"[WEB] StayPresent sunucusu {port} portunda başlatılıyor...")
    
    # StayPresent sunucusunu başlat
    staypresent.run(port=port)

if __name__ == "__main__":
    # 1. ADIM: Web sunucusunu arka planda başlat (Thread)
    web_thread = threading.Thread(target=start_web_server)
    web_thread.daemon = True # Ana program kapanırsa bu thread de kapansın
    web_thread.start()

    # 2. ADIM: Botu ANA THREAD'de başlat
    # Asyncio (botun kalbi) sadece ana thread'de çalışabilir, bu yüzden burada çalıştırıyoruz.
    print("[BOT] Telegram Botu ana thread'de başlatılıyor...")
    run_bot()
