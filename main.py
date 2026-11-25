import os
import threading
import time
from bot import main as run_bot
import staypresent

def start_bot():
    # Render'ın sahte web sunucusunu başlatması için 2 saniye bekle
    time.sleep(2) 
    run_bot()

if __name__ == "__main__":
    # Botu arka planda (ayrı bir iş parçacığında) çalıştır
    bot_thread = threading.Thread(target=start_bot)
    bot_thread.daemon = True
    bot_thread.start()

    # Render'ın beklediği HTTP portunu (web sunucusunu) başlat
    port = int(os.getenv("PORT", 8080))
    print(f"Web sunucusu {port} portunda başlatılıyor. Bot 7/24 ayakta kalacak.")
    staypresent.run(port=port)