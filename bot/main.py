import os
import logging
import asyncio
import signal
import sys
import traceback
from datetime import datetime
from telegram.ext import Application, PicklePersistence
from telegram import Update
from config import TOKEN, logger
from handlers import setup_handlers
from database.db_manager import DatabaseManager
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# Geliştirme modunda mı?
DEV_MODE = os.environ.get('DEV_MODE', 'False').lower() == 'true'

# Loglama ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG if DEV_MODE else logging.INFO
)
logger = logging.getLogger(__name__)

# Kapanma olayı
shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    """Sinyal yakalayıcı"""
    logger.info("Sinyal alındı, bot güvenli bir şekilde kapatılıyor...")
    # Event'i asenkron olarak set etmek için asyncio.run_coroutine_threadsafe kullanıyoruz
    if asyncio.get_event_loop().is_running():
        shutdown_event.set()
    else:
        # Eğer event loop çalışmıyorsa, doğrudan çıkış yap
        logger.info("Event loop çalışmıyor, doğrudan çıkış yapılıyor...")
        os._exit(0)

async def main():
    """Bot başlatma fonksiyonu"""
    app = None
    try:
        # Veritabanı bağlantısı ve kurulumu
        logger.info("Veritabanı kurulumu başlatılıyor...")
        print("Veritabanı kurulumu başlatılıyor...")
        
        # Veritabanı URL'sini kontrol et
        db_url = os.getenv('DATABASE_URL')
        logger.info(f"Veritabanı URL: {db_url}")
        print(f"Veritabanı URL: {db_url}")
        
        db_manager = DatabaseManager()
        setup_success = db_manager.setup_database()
        
        if not setup_success:
            logger.error("Veritabanı kurulumu başarısız oldu!")
            print("Veritabanı kurulumu başarısız oldu!")
            return
        
        logger.info("Veritabanı kurulumu tamamlandı.")
        
        # Geliştirme modunda ise, hot-reload için bilgi mesajı
        if DEV_MODE:
            logger.info("Geliştirme modu aktif! Kod değişiklikleri için Docker volume mapping kullanılıyor.")
        
        # Persistence'ı yapılandır
        persistence = PicklePersistence(
            filepath="bot_data.pickle",
            single_file=True,
            update_interval=60
        )
        
        # Bot uygulamasını oluştur
        app = Application.builder()\
            .token(os.environ.get("BOT_TOKEN"))\
            .persistence(persistence)\
            .concurrent_updates(True)\
            .arbitrary_callback_data(True)\
            .build()
        
        # Handler'ları ayarla
        setup_handlers(app)
        
        # Botu başlat
        logger.info("Bot başlatılıyor...")
        await app.initialize()
        await app.start()
        
        # Polling başlat
        logger.info("Bot polling başlatılıyor...")
        await app.updater.start_polling(
            allowed_updates=[
                Update.MESSAGE,
                Update.EDITED_MESSAGE,
                Update.CHANNEL_POST,
                Update.EDITED_CHANNEL_POST,
                Update.CALLBACK_QUERY
            ],
            drop_pending_updates=False,
            timeout=30,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30,
            pool_timeout=30
        )
        
        logger.info("🚀 Bot başarıyla başlatıldı!")
        
        # Botu çalışır durumda tut, shutdown_event bekle
        await shutdown_event.wait()
        
        # Shutdown_event tetiklendiğinde buraya gelir
        logger.info("🛑 Bot güvenli bir şekilde kapatılıyor...")
        
    except Exception as e:
        logger.error(f"Bot başlatma hatası: {str(e)}")
        print(f"Bot başlatma hatası: {str(e)}")
    finally:
        # Botu kapat
        if app is not None:
            try:
                logger.info("Bot servisleri kapatılıyor...")
                await app.updater.stop()
                await app.stop()
                # app.shutdown() metodu kaldırıldı
            except Exception as e:
                logger.error(f"Bot kapatma hatası: {str(e)}")
        
        logger.info("🔚 Bot başarıyla kapatıldı!")

if __name__ == "__main__":
    # Sinyal handler'ları ayarla
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Bot'u başlat
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Klavye kesintisi algılandı, çıkış yapılıyor...")
    except Exception as e:
        logger.error(f"Beklenmeyen hata: {str(e)}")
        print(f"Beklenmeyen hata: {str(e)}") 