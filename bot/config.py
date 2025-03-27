import os
import logging
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# Bot token'ı
TOKEN = os.getenv('BOT_TOKEN')
SUPER_ADMIN_ID = int(os.getenv('SUPER_ADMIN_ID'))  # Süper admin Telegram ID'si
NOWPAYMENTS_API_KEY = os.getenv('NOWPAYMENTS_API_KEY')  # NowPayments API anahtarı
NOTIFICATION_BOT_TOKEN = os.getenv('NOTIFICATION_BOT_TOKEN')  # Bildirim botu token'ı

# ImgBB API için gerekli ayarlar
IMGBB_API_KEY = os.environ.get('IMG_API_KEY', '')
IMGBB_UPLOAD_URL = os.environ.get('IMGBB_UPLOAD_URL')

# Logger ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # DEBUG yerine INFO kullan
)

# Gereksiz logları kapat
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.INFO)

# Logger'ı oluştur
logger = logging.getLogger(__name__)

class TurkishLogFormatter(logging.Formatter):
    def __init__(self):
        super().__init__('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    def format(self, record):
        # Token'ı içeren tüm mesajları maskele
        if isinstance(record.msg, str):
            if TOKEN in record.msg:
                record.msg = record.msg.replace(TOKEN, '**********')
            
            # HTTP request loglarını maskele
            if 'api.telegram.org/bot' in record.msg:
                record.msg = record.msg.replace(f'bot{TOKEN}', 'bot**********')
                # getUpdates loglarını özelleştir
                if 'getUpdates' in record.msg:
                    return None  # Bu logu tamamen gizle

        # Özel mesaj çevirileri
        msg_str = str(record.msg)
        if 'Application started' in msg_str:
            record.msg = '🚀 Bot başarıyla başlatıldı!'
        elif 'Application is stopping' in msg_str:
            record.msg = '🛑 Bot kapatılıyor...'
        elif 'Application.stop() complete' in msg_str:
            record.msg = '🔚 Bot başarıyla kapatıldı!'  # None yerine özel mesaj
        elif 'Error while getting Updates' in msg_str:
            record.msg = '⛔️ Güncelleme alınırken hata oluştu!'
        
        try:
            return super().format(record)
        except TypeError:
            return None  # Eğer format hatası olursa logu atla

# Çift loglamayı önlemek için mevcut handlers'ları temizle
root = logging.getLogger()
if root.handlers:
    for handler in root.handlers:
        root.removeHandler(handler)

# Logging ayarları
formatter = TurkishLogFormatter()

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# File handler
file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setFormatter(formatter)

# Ana logger yapılandırması
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[console_handler, file_handler],
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# HTTPX loglarını yapılandır
httpx_logger = logging.getLogger('httpx')
httpx_logger.setLevel(logging.WARNING)  # Sadece uyarı ve hataları göster

# Telegram loglarını yapılandır
telegram_logger = logging.getLogger('telegram')
telegram_logger.handlers = []  # Mevcut handler'ları temizle
telegram_logger.addHandler(console_handler)
telegram_logger.addHandler(file_handler)
telegram_logger.propagate = False  # Çift loglamayı önle

logger.propagate = False  # Çift loglamayı önle

logger.info('🔧 Bot yapılandırması yüklendi') 