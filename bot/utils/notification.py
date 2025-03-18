import requests
import logging
from sqlalchemy import text
from bot.config import NOTIFICATION_BOT_TOKEN, SUPER_ADMIN_ID, logger
from bot.database.db_manager import DatabaseManager

async def send_payment_notification(payment_data, admin_id=None):
    """
    Ödeme bildirimi gönder
    
    Args:
        payment_data (dict): Ödeme verileri
        admin_id (int, optional): Bildirim gönderilecek admin ID'si. Eğer None ise, süper admine gönderilir.
    
    Returns:
        bool: Başarılı ise True, değilse False
    """
    try:
        # Bildirim her zaman süper admine gönderilir
        user_id = SUPER_ADMIN_ID
        
        # Ödeme durumu
        payment_status = payment_data.get("payment_status", "bilinmiyor")
        payment_id = payment_data.get("payment_id", "bilinmiyor")
        price_amount = payment_data.get("price_amount", "bilinmiyor")
        price_currency = payment_data.get("price_currency", "TRY")
        pay_amount = payment_data.get("pay_amount", "bilinmiyor")
        pay_currency = payment_data.get("pay_currency", "USDTTRC20")
        
        # Admin bilgilerini al
        # Önce payment_data'dan admin_id'yi al
        admin_id = payment_data.get("admin_id")
        
        # Eğer payment_data'da admin_id yoksa, order_description'dan almayı dene
        if not admin_id:
            order_description = payment_data.get("order_description", "")
            if order_description and order_description.startswith("bakiye_"):
                try:
                    admin_id = order_description.split("_")[1]
                except (IndexError, ValueError):
                    admin_id = "bilinmiyor"
        
        # Admin adını veritabanından al
        admin_name = "İsimsiz Admin"
        admin_username = "Bilinmiyor"
        
        # payment_data'dan admin bilgilerini al (varsa)
        if payment_data.get("admin_name"):
            admin_name = payment_data.get("admin_name")
        if payment_data.get("admin_username"):
            admin_username = payment_data.get("admin_username")
        
        # Eğer payment_data'da yoksa ve admin_id varsa, veritabanından almayı dene
        if admin_id and (admin_name == "İsimsiz Admin" or admin_username == "Bilinmiyor"):
            try:
                db = DatabaseManager()
                # Veritabanından admin bilgilerini al
                with db.engine.connect() as conn:
                    logger.info(f"Admin bilgisi sorgulanıyor: admin_id={admin_id}")
                    result = conn.execute(text("""
                        SELECT admin_name FROM group_admins 
                        WHERE user_id = :user_id
                    """), {"user_id": admin_id})
                    admin_data = result.fetchone()
                    logger.info(f"Veritabanı sorgu sonucu: {admin_data}")
                    if admin_data and admin_data[0]:
                        admin_name = admin_data[0]
                        logger.info(f"Admin adı veritabanından alındı: {admin_name}")
                    else:
                        logger.warning(f"Admin adı veritabanında bulunamadı: {admin_id}")
            except Exception as e:
                logger.error(f"Admin bilgisi alma hatası: {str(e)}")
        
        # Durum emojisi
        status_emoji = "✅" if payment_status in ["confirmed", "finished"] else "⏳"
        
        # Bildirim mesajı
        message = (
            f"{status_emoji} Ödeme Bildirimi\n\n"
            f"👤 Admin: {admin_name}\n"
            f"🆔 Admin ID: {admin_id}\n"
            f"👨‍💻 Kullanıcı Adı: {admin_username}\n"
            f"💰 Tutar: {price_amount} {price_currency}\n"
            f"💲 Ödenen: {pay_amount} {pay_currency}\n"
            f"🆔 Ödeme ID: {payment_id}\n"
            f"📊 Durum: {payment_status.upper()}"
        )
        
        # Bildirim token'ı kontrol et
        if not NOTIFICATION_BOT_TOKEN or NOTIFICATION_BOT_TOKEN == "your_notification_bot_token_here":
            logger.warning("Bildirim botu token'ı ayarlanmamış. Bildirim gönderilemiyor.")
            return False
        
        # Telegram API URL
        url = f"https://api.telegram.org/bot{NOTIFICATION_BOT_TOKEN}/sendMessage"
        
        # API isteği için gerekli parametreler
        payload = {
            "chat_id": user_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        # API isteği gönder
        try:
            response = requests.post(url, json=payload)
            
            # Yanıtı kontrol et
            if response.status_code == 200:
                logger.info(f"Ödeme bildirimi gönderildi: {user_id}")
                return True
            else:
                logger.error(f"Ödeme bildirimi gönderme hatası: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Bildirim gönderme isteği hatası: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"Ödeme bildirimi gönderme hatası: {str(e)}")
        return False 