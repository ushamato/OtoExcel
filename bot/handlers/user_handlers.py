from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot.config import logger, SUPER_ADMIN_ID, NOWPAYMENTS_API_KEY, NOTIFICATION_BOT_TOKEN, TOKEN
from bot.database.db_manager import DatabaseManager
from bot.utils.decorators import super_admin_required, admin_required
from bot.utils.notification import send_payment_notification
from datetime import datetime
from functools import wraps
import requests
import json
import os
from sqlalchemy import text

# Conversation states
WAITING_AMOUNT = 1

def authorized_group_required(func):
    """Komutun sadece yetkili gruplarda çalışmasını sağlayan dekoratör"""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat
        user = update.effective_user
        
        # Özel mesajlarda çalışmasına izin ver (admin komutları için)
        if chat.type == 'private':
            return await func(self, update, context, *args, **kwargs)
        
        # Süper admin her yerde çalıştırabilir
        if user.id == SUPER_ADMIN_ID:
            return await func(self, update, context, *args, **kwargs)
            
        # Grup yetkili mi kontrol et
        is_authorized = await self.db.is_authorized_group(chat.id)
        if not is_authorized:
            await update.message.reply_text(
                "⛔️ Bu grup yetkili bir admin tarafından eklenmemiş!\n\n"
                "ℹ️ Botun çalışması için bir admin tarafından grubun eklenmesi gerekiyor."
            )
            return
        
        return await func(self, update, context, *args, **kwargs)
    return wrapper

class UserHandlers:
    def __init__(self):
        self.db = DatabaseManager()  # DBManager -> DatabaseManager
        self.payment_check_job = None
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bot başlatma komutu"""
        try:
            await update.message.reply_text(
                "👋 Merhaba! Ben OttoExcel Bot.\n\n"
                "📅 Sıkıcı Excel işlerinizi Telegram'da otomatikleştirmek için tasarlandım:\n\n"
                "✅ Tek komutla rapor oluştur\n\n"
                "✅ Telegram dışına çıkmana gerek yok\n\n"
                "✅ Tüm verileriniz şifrelenmiş olarak saklanır\n\n"                        
                "🔐 Güvenli & Hızlı Yükleme:\n"
                "Kripto ile anonim ödeme yap, bakiyen anında aktif olsun.\n\n"
                "⚡ 7/24 Hizmet | ℹ️ Başlamak için:\n"
                "/bakiyeyukle komutunu kullan, saniyeler içinde üretim yap!"
            )
        except Exception as e:
            logger.error(f"Start komutu hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Yardım komutu"""
        try:
            user = update.effective_user
            is_super_admin = user.id == SUPER_ADMIN_ID
            is_admin = await self.db.is_group_admin(user.id)
            
            # Yetkisiz kullanıcılar için yönlendirme mesajı
            if not is_admin and user.id != SUPER_ADMIN_ID:
                await update.message.reply_text(
                    "ℹ️ Bot komutlarına erişmek için önce hesabınıza bakiye yüklemeniz gerekiyor.\n\n"
                    "📲 Bakiye yüklemek için: /bakiyeyukle\n\n"
                    "💡 Ödemeniz onaylandıktan sonra tüm komutlara erişebileceksiniz!"
                )
                return
            
            # Yetkili kullanıcılar için komut listesi
            help_text = """ Kullanılabilir Komutlar:

📋 Form İşlemleri:
📝 /formekle - Yeni form oluştur
📊 /formlar - Mevcut formları listele
📄 /form - Form verisi gir
📈 /rapor - Form verilerini Excel olarak al

💰 Bakiye İşlemleri:
💵 /bakiye - Mevcut bakiyeyi gösterir
💳 /bakiyeyukle - Bakiye yükleme işlemi başlatır

🏢 Grup İşlemleri:
🔍 /chatid - Sohbet ID'sini gösterir
📂 /gruplar - Grupları listeler
➕ /grupekle - Yeni grup ekler
➖ /grupsil - Grup siler"""

            # Süper admin için ek komutları göster
            if is_super_admin:
                help_text += """

👑 Süper Admin Komutları:
👤 /adminekle - Yeni admin ekler
🚫 /adminsil - Admin yetkisi kaldırır
📋 /adminler - Tüm adminleri listeler
➕ /bakiyeekle - Admine bakiye ekler
➖ /bakiyesil - Adminden bakiye siler"""

            help_text += "\n\n❓ Komutlara tıkladığızda bot detaylı kullanım bilgisi verecektir."
            help_text += "\n\n⚠️ Önemli: Bot'u gruplara eklerken, tüm komutların düzgün çalışabilmesi için bota yönetici yetkisi verilmelidir."

            await update.message.reply_text(help_text)
            
        except Exception as e:
            logger.error(f"Yardım komutu hatası: {str(e)}")
            await update.message.reply_text("⛔️ Yardım gösterilirken bir hata oluştu. Lütfen daha sonra tekrar deneyin.")

    @authorized_group_required
    @admin_required
    async def get_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bakiye sorgula"""
        try:
            user_id = update.effective_user.id
            balance = await self.db.bakiye_getir(user_id)
            
            await update.message.reply_text(
                f"💰 Mevcut kullanım hakkınız: {balance}"
            )
            
        except Exception as e:
            logger.error(f"Bakiye sorgulama hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    @authorized_group_required
    @admin_required
    async def list_forms(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Formları listele"""
        try:
            user = update.effective_user
            is_super_admin = user.id == SUPER_ADMIN_ID
            
            # Formları getir
            forms = await self.db.get_forms(None if is_super_admin else user.id)
            
            if forms and len(forms) > 0:
                message = "📋 Mevcut Formlar:\n\n"
                for form in forms:
                    message += f"📝 {form['form_name']}\n"
                    fields = form['fields'].split(',')
                    message += "🔹 Alanlar: " + ", ".join(fields) + "\n\n"
            else:
                if is_super_admin:
                    message = "⛔️ Henüz hiç form oluşturulmamış."
                else:
                    message = "⛔️ Size ait hiç form bulunmamaktadır."
            
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Form listeleme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    @authorized_group_required
    @admin_required
    async def get_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Rapor oluştur"""
        try:
            args = context.args
            if not args:
                await update.message.reply_text(
                    "⛔️ Lütfen form adını belirtin!\n\n"
                    "📝 Doğru Kullanım:\n"
                    "/rapor form_adi\n\n"
                    "Örnek:\n"
                    "/rapor yahoo\n\n"
                    "📅 Belirli bir tarih aralığı için rapor almak isterseniz:\n"
                    "/rapor form_adi GG.AA.YYYY GG.AA.YYYY\n\n"
                    "Örnek:\n"
                    "/rapor yahoo 01.03.2025 10.03.2025"
                )
                return
            
            form_name = args[0].lower()
            user_id = update.effective_user.id
            is_super_admin = user_id == SUPER_ADMIN_ID
            
            # Tarih parametrelerini kontrol et
            start_date = None
            end_date = None
            
            if len(args) >= 3:
                try:
                    # GG.AA.YYYY formatını datetime objesine çevir
                    start_date = datetime.strptime(args[1], "%d.%m.%Y")
                    end_date = datetime.strptime(args[2], "%d.%m.%Y")
                    
                    # Bitiş tarihi için saat 23:59:59'a ayarla
                    end_date = end_date.replace(hour=23, minute=59, second=59)
                    
                    logger.info(f"Tarih aralığı belirlendi: {start_date} - {end_date}")
                except ValueError:
                    await update.message.reply_text(
                        "⛔️ Geçersiz tarih formatı!\n\n"
                        "📅 Tarih formatı GG.AA.YYYY şeklinde olmalıdır.\n"
                        "Örnek: 01.03.2025"
                    )
                    return
            
            # Rapor oluştur
            excel_file = await self.db.generate_report(
                form_name=form_name,
                admin_id=user_id,
                start_date=start_date,
                end_date=end_date,
                is_super_admin=is_super_admin
            )
            
            if excel_file:
                # Tarih bilgisi varsa dosya adına ekle
                filename = f"{form_name}_rapor"
                if start_date and end_date:
                    filename += f"_{start_date.strftime('%d%m%Y')}-{end_date.strftime('%d%m%Y')}"
                filename += ".xlsx"
                
                # Excel dosyasını gönder
                caption = f"📊 {form_name.capitalize()} Raporu"
                if start_date and end_date:
                    caption += f" ({start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')})"
                
                await update.message.reply_document(
                    document=excel_file,
                    filename=filename,
                    caption=caption
                )
            else:
                await update.message.reply_text(
                    "⛔️ Rapor oluşturulamadı!\n\n"
                    "Olası nedenler:\n"
                    "• Form bulunamadı\n"
                    "• Henüz veri girişi yapılmamış\n"
                    "• Veritabanı hatası"
                )
            
        except Exception as e:
            logger.error(f"Rapor oluşturma hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    async def chatid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sohbet ID'sini ve türünü gösterir"""
        try:
            chat = update.effective_chat
            chat_type = chat.type.capitalize()
            
            message = (
                f"ℹ️ Sohbet Bilgileri:\n\n"
                f"🆔 Chat ID: {chat.id}\n"
                f"📝 Tür: {chat_type}\n"
            )
            
            if chat.title:  # Grup veya kanal ise başlığı da göster
                message += f"📌 Başlık: {chat.title}"
            
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Chat ID gösterme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    @authorized_group_required
    @admin_required
    async def list_groups(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Grupları listele"""
        try:
            user = update.effective_user
            is_super_admin = user.id == SUPER_ADMIN_ID
            
            # Grupları getir
            groups = self.db.get_groups(None if is_super_admin else user.id)
            
            if groups and len(groups) > 0:
                message = "🏢 Gruplar:\n\n"
                for group in groups:
                    group_id, group_name, db_id = group
                    message += f"📌 {group_name}\n"
                    message += f"🆔 Chat ID: {group_id}\n"
                    message += f"📊 ID: {db_id}\n\n"
            else:
                if is_super_admin:
                    message = "⛔️ Henüz hiç grup bulunmamaktadır."
                else:
                    message = "⛔️ Yönettiğiniz hiç grup bulunmamaktadır."
            
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Grup listeleme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    @admin_required
    async def add_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Grup ekle"""
        try:
            # Süper admin kontrolü
            user = update.effective_user
            is_super_admin = user.id == SUPER_ADMIN_ID
            chat = update.effective_chat

            # Süper admin için eski mantık (ID ile ekleme)
            if is_super_admin:
                args = context.args
                if len(args) < 2:
                    await update.message.reply_text(
                        "⛔️ Hatalı format!\n\n"
                        "📝 Doğru Kullanım:\n"
                        "/grupekle GrupID GrupAdı\n\n"
                        "Örnek:\n"
                        "/grupekle -1234567890 Test Grubu"
                    )
                    return

                try:
                    group_id = int(args[0])
                    group_name = " ".join(args[1:])
                except ValueError:
                    await update.message.reply_text("⛔️ Grup ID sayısal olmalıdır!")
                    return
            # Normal admin için yeni mantık (otomatik ID)
            else:
                # Grup kontrolü
                if chat.type not in ['group', 'supergroup']:
                    await update.message.reply_text(
                        "⛔️ Bu komut sadece gruplarda kullanılabilir!\n\n"
                        "ℹ️ Grubu eklemek için grupta bu komutu kullanın."
                    )
                    return

                args = context.args
                if not args:
                    await update.message.reply_text(
                        "⛔️ Hatalı format!\n\n"
                        "📝 Doğru Kullanım:\n"
                        "/grupekle GrupAdı\n\n"
                        "Örnek:\n"
                        "/grupekle Test Grubu"
                    )
                    return

                group_id = chat.id
                group_name = " ".join(args)

            # Grup zaten ekli mi kontrolü
            group_exists = await self.db.get_group_name(group_id)
            if group_exists:
                await update.message.reply_text("⛔️ Bu grup zaten eklenmiş!")
                return

            # Grubu ekle
            success = await self.db.add_group(group_id, group_name, user.id)

            if success:
                await update.message.reply_text(
                    f"✅ Grup başarıyla eklendi!\n\n"
                    f"🏢 Grup: {group_name}\n"
                    f"🆔 ID: {group_id}"
                )
            else:
                await update.message.reply_text("⛔️ Grup eklenirken bir hata oluştu!")

        except Exception as e:
            logger.error(f"Grup ekleme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    @authorized_group_required
    @admin_required
    async def remove_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Grup sil"""
        try:
            user = update.effective_user
            is_super_admin = user.id == SUPER_ADMIN_ID
            chat = update.effective_chat

            # Normal admin için otomatik ID kullan
            if not is_super_admin:
                args = context.args
                if chat.type not in ['group', 'supergroup'] and not args:
                    await update.message.reply_text(
                        "⛔️ Bu komutu kullanmak için iki seçeneğiniz var:\n\n"
                        "1️⃣ Grupta bu komutu kullanın\n"
                        "2️⃣ ID ile silmek için:\n"
                        "/grupsil DB_ID\n\n"
                        "Örnek:\n"
                        "/grupsil 3"
                    )
                    return

                # IDile silme
                if args:
                    try:
                        db_id = int(args[0])
                        group_info = self.db.get_group_by_db_id(db_id)
                        if not group_info:
                            await update.message.reply_text("⛔️ Belirtilen DB ID'ye sahip grup bulunamadı!")
                            return
                        group_id = group_info['group_id']
                    except ValueError:
                        await update.message.reply_text("⛔️ IDsayısal olmalıdır!")
                        return
                else:
                    group_id = chat.id

            # Süper admin için ID parametresi gerekli
            else:
                args = context.args
                if not args:
                    await update.message.reply_text(
                        "⛔️ Hatalı format!\n\n"
                        "📝 Doğru Kullanım:\n"
                        "/grupsil ID\n\n"
                        "ID olarak:\n"
                        "• Chat ID (-1234567890)\n"
                        "• ID(3)\n"
                        "kullanabilirsiniz."
                    )
                    return

                try:
                    input_id = int(args[0])
                    # IDkontrolü
                    group_info = self.db.get_group_by_db_id(input_id)
                    if group_info:
                        group_id = group_info['group_id']
                    else:
                        # Chat ID olarak dene
                        group_id = input_id
                except ValueError:
                    await update.message.reply_text("⛔️ ID sayısal olmalıdır!")
                    return

            # Grup adını al
            group_name = await self.db.get_group_name(group_id)
            if not group_name:
                await update.message.reply_text("⛔️ Belirtilen ID'ye sahip grup bulunamadı!")
                return

            # Grubu sil
            success = await self.db.remove_group(group_id, user.id)
            if success:
                await update.message.reply_text(
                    f"✅ Grup başarıyla silindi!\n\n"
                    f"🏢 Grup: {group_name}\n"
                    f"🆔 ID: {group_id}"
                )
            else:
                if is_super_admin:
                    await update.message.reply_text("⛔️ Grup silinirken bir hata oluştu!")
                else:
                    await update.message.reply_text(
                        "⛔️ Bu grubu silme yetkiniz yok!\n\n"
                        "ℹ️ Sadece yöneticisi olduğunuz grupları silebilirsiniz."
                    )

        except Exception as e:
            logger.error(f"Grup silme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    async def load_credits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bakiye yükleme işlemi başlat"""
        try:
            # Kullanıcıya bakiye yükleme bilgilerini sor
            await update.message.reply_text(
                "💰 Bakiye Yükleme İşlemi\n\n"
                "📝 Yüklemek istediğiniz tutarı TL cinsinden yazınız.\n"
                "ℹ️ Minimum yükleme tutarı: 500₺\n"
                "ℹ️ Form başı ücret: 10₺"
            )
            
            # Conversation state'i ayarla
            context.user_data['conversation_state'] = WAITING_AMOUNT
            return WAITING_AMOUNT
            
        except Exception as e:
            logger.error(f"Bakiye yükleme başlatma hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    async def get_nowpayments_address(self, amount, admin_id, currency="TRY"):
        """NowPayments API'sinden TRC20 USDT adresi al"""
        try:
            # API endpoint
            url = "https://api.nowpayments.io/v1/payment"
            
            # Admin bilgilerini değişkenlere tanımla
            admin_name = "İsimsiz Kullanıcı"
            admin_username = "Bilinmiyor"
            
            try:
                # Kullanıcının admin olup olmadığını kontrol et
                is_admin = await self.db.is_admin(str(admin_id))
                
                # Kullanıcı admin ise veritabanından bilgilerini al
                if is_admin:
                    # Veritabanından admin adını al
                    with self.db.engine.connect() as conn:
                        result = conn.execute(text("""
                            SELECT admin_name FROM group_admins 
                            WHERE user_id = :user_id
                        """), {"user_id": admin_id})
                        admin_data = result.fetchone()
                        if admin_data and admin_data[0]:
                            admin_name = admin_data[0]
                
                # Telegram API'den kullanıcı adını almaya çalış
                try:
                    from telegram import Bot
                    
                    # Bot oluştur
                    bot = Bot(token=TOKEN)
                    
                    # Kullanıcı bilgilerini al
                    user = await bot.get_chat(admin_id)
                    
                    # Kullanıcı adını al (varsa)
                    if user.username:
                        admin_username = user.username
                    else:
                        # Kullanıcı adı yoksa, adını kullan
                        admin_username = user.first_name
                        if user.last_name:
                            admin_username += f" {user.last_name}"
                    
                    # Veritabanından alınamadıysa (admin değilse), Telegram'dan aldığımız ismi kullan
                    if admin_name == "İsimsiz Kullanıcı":
                        admin_name = admin_username
                    
                    logger.info(f"Kullanıcı bilgileri Telegram API'den alındı: {admin_username}")
                except Exception as e:
                    logger.error(f"Telegram API'den kullanıcı bilgileri alma hatası: {str(e)}")
            except Exception as e:
                logger.error(f"Kullanıcı bilgisi alma hatası: {str(e)}")
            
            # API isteği için gerekli parametreler
            payload = {
                "price_amount": amount,
                "price_currency": currency,  # TL cinsinden
                "pay_currency": "USDTTRC20",
                "order_id": f"bakiye_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "order_description": f"bakiye_{admin_id}"  # Admin ID'yi order_description'a ekle
            }
            
            # API isteği için gerekli headers
            headers = {
                "x-api-key": NOWPAYMENTS_API_KEY,
                "Content-Type": "application/json"
            }
            
            # API isteği gönder
            response = requests.post(url, json=payload, headers=headers)
            
            # Yanıtı kontrol et (201 Created da başarılı bir yanıttır)
            if response.status_code == 200 or response.status_code == 201:
                data = response.json()
                logger.info(f"NowPayments API yanıtı: {data}")
                
                # Ödeme oluşturulduğunda bildirim gönder (hata olsa bile devam et)
                try:
                    payment_data = {
                        "payment_status": "waiting",
                        "payment_id": data.get("payment_id"),
                        "price_amount": amount,
                        "price_currency": currency,
                        "pay_amount": data.get("pay_amount"),
                        "pay_currency": data.get("pay_currency", "USDTTRC20"),
                        "order_description": f"bakiye_{admin_id}",
                        "admin_id": admin_id,
                        "admin_name": admin_name,
                        "admin_username": admin_username
                    }
                    await send_payment_notification(payment_data)
                except Exception as e:
                    logger.error(f"Bildirim gönderme hatası (önemsiz): {str(e)}")
                
                # Ödeme bilgilerini döndür
                return {
                    "success": True,
                    "pay_address": data.get("pay_address"),
                    "payment_id": data.get("payment_id"),
                    "pay_amount": data.get("pay_amount"),
                    "pay_currency": data.get("pay_currency", "USDTTRC20")
                }
            else:
                logger.error(f"NowPayments API hatası: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"API Hatası: {response.status_code}"
                }
            
        except Exception as e:
            logger.error(f"NowPayments API hatası: {str(e)}")
            return {
                "success": False,
                "error": f"API Hatası: {str(e)}"
            }

    async def process_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yükleme miktarını işle"""
        try:
            user_input = update.message.text.strip()
            user = update.effective_user
            
            # Sayısal değer kontrolü
            try:
                amount = float(user_input)
            except ValueError:
                await update.message.reply_text(
                    "⛔️ Geçersiz tutar! Lütfen sayısal bir değer giriniz.\n\n"
                    "Örnek: 500"
                )
                return WAITING_AMOUNT
            
            # Minimum tutar kontrolü
            if amount < 500:
                await update.message.reply_text(
                    "⛔️ Minimum yükleme tutarı 500₺ olmalıdır!\n\n"
                    "Sistem altyapımız gereği 500₺ altındaki işlemleri kabul edemiyoruz."
                )
                return WAITING_AMOUNT
            
            # NOT: Admin ekleme işlemi ödeme başarılı olduktan sonra yapılacak
            # Kullanıcıya ödeme adresini gösterme aşamasına geç
            
            # İşlem başlatıldığını bildir
            await update.message.reply_text(
                "⏳ Ödeme adresi oluşturuluyor, lütfen bekleyin..."
            )
            
            # NowPayments API'sinden ödeme adresi al (doğrudan TL cinsinden)
            payment_info = await self.get_nowpayments_address(amount, user.id, "TRY")
            
            if payment_info["success"]:
                # Para birimini daha güzel formatta göster
                currency_display = "USDT (TRC20)"
                
                # Ödeme bilgilerini göster
                await update.message.reply_text(
                    f"💰 Bakiye Yükleme Bilgileri\n\n"
                    f"💵 Yüklenecek Tutar: {amount}₺\n"
                    f"💲 USDT Karşılığı: `{payment_info['pay_amount']}` {currency_display}\n\n"
                    f"📲 Lütfen aşağıdaki TRC20 adresine ödeme yapınız:\n\n"
                    f"Tutar: `{payment_info['pay_amount']}` {currency_display}\n"
                    f"Adres: `{payment_info['pay_address']}`\n\n"
                    f"⚠️ ÖNEMLİ BİLGİLENDİRME:\n"
                    f"• Ödeme adresi 20 dakika süreyle geçerlidir.\n"
                    f"• Güvenliğiniz için süre aşımında işlemi yeniden başlatınız.\n"
                    f"• Ödeme onaylandığında bakiyeniz otomatik olarak güncellenecektir.\n"
                    f"• Yalnızca TRC20 ağı üzerinden transfer yapınız.\n"
                    f"• Farklı ağlar kullanıldığında ödeme kaybı yaşanabilir.",
                    parse_mode="Markdown"
                )
                
                # Ödeme bilgilerini kullanıcı verilerine kaydet
                context.user_data["payment_info"] = {
                    "amount_tl": amount,
                    "amount_usdt": payment_info["pay_amount"],
                    "payment_id": payment_info["payment_id"],
                    "pay_address": payment_info["pay_address"],
                    "admin_id": user.id,
                    "start_time": datetime.now().timestamp()
                }
                
                return ConversationHandler.END
            else:
                await update.message.reply_text(
                    f"⛔️ Ödeme adresi oluşturulurken bir hata oluştu!\n\n"
                    f"Hata: {payment_info.get('error', 'Bilinmeyen hata')}\n\n"
                    f"Lütfen daha sonra tekrar deneyiniz veya destek ekibimizle iletişime geçiniz."
                )
                return ConversationHandler.END
                
        except Exception as e:
            logger.error(f"Ödeme miktarı işleme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")
            return ConversationHandler.END
    
    async def check_payment_status_job(self, context: ContextTypes.DEFAULT_TYPE):
        """Ödeme durumunu kontrol etmek için zamanlayıcı işi"""
        try:
            # Ödeme bilgilerini al
            job_data = context.job.data
            payment_id = job_data.get("payment_id")
            admin_id = job_data.get("admin_id")
            
            # Ödeme durumunu kontrol et
            result = await self.check_payment_status(payment_id, admin_id)
            
            # Eğer ödeme tamamlandıysa, zamanlayıcıyı durdur
            if result:
                context.job.schedule_removal()
                
        except Exception as e:
            logger.error(f"Ödeme durumu kontrol işi hatası: {str(e)}")

    async def cancel_load_credits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bakiye yükleme işlemini iptal et"""
        await update.message.reply_text("❌ Bakiye yükleme işlemi iptal edildi.")
        return ConversationHandler.END

    async def process_nowpayments_ipn(self, payment_data):
        """NowPayments IPN callback'ini işle"""
        try:
            # Ödeme verilerini logla
            logger.info(f"NowPayments IPN bildirimi alındı: {payment_data}")
            
            # Ödeme durumunu kontrol et
            payment_status = payment_data.get("payment_status")
            payment_id = payment_data.get("payment_id")
            
            # Admin ID'yi al
            admin_id = None
            order_description = payment_data.get("order_description", "")
            if order_description and order_description.startswith("bakiye_"):
                try:
                    admin_id = order_description.split("_")[1]
                except (IndexError, ValueError):
                    admin_id = None
                    logger.error(f"Admin ID alınamadı: {order_description}")
            
            # Kullanıcı bilgilerini tanımla
            admin_name = "İsimsiz Kullanıcı"
            admin_username = "Bilinmiyor"
            
            if admin_id:
                try:
                    # Önce kullanıcının admin olup olmadığını kontrol et
                    user_is_admin = await self.db.is_admin(str(admin_id))
                    
                    # Telegram API'den kullanıcı bilgilerini al
                    try:
                        from telegram import Bot
                        bot = Bot(token=TOKEN)
                        user = await bot.get_chat(admin_id)
                        
                        # Kullanıcı adını al (varsa)
                        if user.username:
                            admin_username = user.username
                        else:
                            # Kullanıcı adı yoksa, adını kullan
                            admin_username = user.first_name
                            if user.last_name:
                                admin_username += f" {user.last_name}"
                        
                        # Telegram'dan alınan ismi varsayılan olarak kullan 
                        admin_name = admin_username
                                
                        # Kullanıcı admin değilse, ve ödeme başarılıysa admin yap
                        if not user_is_admin and (payment_status == "confirmed" or payment_status == "finished"):
                            # Kullanıcıyı admin olarak ekle (parametrelerin doğru sırasına dikkat et)
                            is_success = await self.db.add_admin(admin_id, admin_username, admin_id)
                            if not is_success:
                                logger.error(f"Admin ekleme hatası: Admin ID: {admin_id}")
                            else:
                                logger.info(f"Kullanıcı başarıyla admin yapıldı: {admin_id} ({admin_username})")
                                
                        # Kullanıcı admin ise veritabanından adını güncelle    
                        elif user_is_admin:
                            # Veritabanından admin adını al
                            with self.db.engine.connect() as conn:
                                result = conn.execute(text("""
                                    SELECT admin_name FROM group_admins 
                                    WHERE user_id = :user_id
                                """), {"user_id": admin_id})
                                admin_data = result.fetchone()
                                if admin_data and admin_data[0]:
                                    admin_name = admin_data[0]
                                    
                        logger.info(f"Kullanıcı bilgileri Telegram API'den alındı: {admin_username}")
                    except Exception as e:
                        logger.error(f"Telegram API'den kullanıcı bilgileri alma hatası: {str(e)}")
                    
                except Exception as e:
                    logger.error(f"Kullanıcı bilgisi alma hatası: {str(e)}")
            
            # Admin bilgilerini ekle
            if admin_id:
                payment_data["admin_id"] = admin_id
                payment_data["admin_name"] = admin_name
                payment_data["admin_username"] = admin_username
            
            # Sadece süper admine bildirim gönder (hata olsa bile devam et)
            try:
                await send_payment_notification(payment_data)
            except Exception as e:
                logger.error(f"Bildirim gönderme hatası (önemsiz): {str(e)}")
            
            if payment_status == "confirmed" or payment_status == "finished":
                # Ödeme tamamlandı, bakiyeyi güncelle
                if admin_id:
                    amount_tl = float(payment_data.get("price_amount"))  # Doğrudan TL miktarını al
                    
                    # TL miktarını kullanım hakkına çevir (10 TL = 1 kullanım hakkı)
                    usage_rights = amount_tl / 10.0
                    
                    # Bakiyeyi güncelle
                    success = await self.db.Bakiye_ekle(admin_id, usage_rights)
                    
                    if success:
                        logger.info(f"Bakiye başarıyla güncellendi: Admin ID: {admin_id}, Admin: {admin_name}, Miktar: {amount_tl}₺, Kullanım Hakkı: {usage_rights}")
                        
                        # Kullanıcıya ödeme onaylandı bilgisi gönder
                        try:
                            from telegram import Bot
                            
                            # Bot oluştur
                            bot = Bot(token=TOKEN)
                            
                            # Kullanıcıya bildirim gönder
                            await bot.send_message(
                                chat_id=admin_id,
                                text=(
                                    f"✅ Ödemeniz onaylandı ve hesabınıza yüklendi!\n\n"
                                    f"💰 Yüklenen Tutar: {amount_tl}₺\n"
                                    f"🔢 Eklenen Kullanım Hakkı: {usage_rights}\n\n"
                                    f"🚀 Artık OttoExcel Bot'un tüm özelliklerini kullanabilirsiniz!\n\n"
                                    f"📋 Kullanabileceğiniz tüm komutları görmek için /yardim yazabilirsiniz.\n\n"
                                    f"🙏 OttoExcel Bot'u tercih ettiğiniz için teşekkür ederiz!"
                                )
                            )
                            logger.info(f"Ödeme onay bildirimi kullanıcıya gönderildi: {admin_id}")
                        except Exception as e:
                            logger.error(f"Kullanıcıya bildirim gönderilirken hata oluştu: {str(e)}")
                        
                        return True
                    else:
                        logger.error(f"Bakiye güncellenirken hata oluştu: Admin ID: {admin_id}, Admin: {admin_name}, Miktar: {amount_tl}₺, Kullanım Hakkı: {usage_rights}")
                        return False
                else:
                    logger.error("Admin ID bulunamadı, bakiye güncellenemedi")
                    return False
            else:
                logger.info(f"Ödeme henüz tamamlanmadı. Durum: {payment_status}")
                return True
                
        except Exception as e:
            logger.error(f"IPN işleme hatası: {str(e)}")
            return False

    async def check_payment_status(self, payment_id, admin_id):
        """Ödeme durumunu kontrol et"""
        try:
            # API endpoint
            url = f"https://api.nowpayments.io/v1/payment/{payment_id}"
            
            # API isteği için gerekli headers
            headers = {
                "x-api-key": NOWPAYMENTS_API_KEY
            }
            
            # Kullanıcı bilgilerini tanımla
            admin_name = "İsimsiz Kullanıcı"
            admin_username = "Bilinmiyor"
            
            try:
                # Kullanıcının admin olup olmadığını kontrol et
                is_admin = await self.db.is_admin(str(admin_id))
                
                # Telegram API'den kullanıcı bilgilerini al
                try:
                    from telegram import Bot
                    
                    # Bot oluştur
                    bot = Bot(token=TOKEN)
                    
                    # Kullanıcı bilgilerini al
                    user = await bot.get_chat(admin_id)
                    
                    # Kullanıcı adını al (varsa)
                    if user.username:
                        admin_username = user.username
                    else:
                        # Kullanıcı adı yoksa, adını kullan
                        admin_username = user.first_name
                        if user.last_name:
                            admin_username += f" {user.last_name}"
                    
                    # Telegram'dan alınan ismi varsayılan olarak kullan
                    admin_name = admin_username
                    
                    # Kullanıcı admin ise veritabanından adını güncelle
                    if is_admin:
                        # Veritabanından admin adını al
                        with self.db.engine.connect() as conn:
                            result = conn.execute(text("""
                                SELECT admin_name FROM group_admins 
                                WHERE user_id = :user_id
                            """), {"user_id": admin_id})
                            admin_data = result.fetchone()
                            if admin_data and admin_data[0]:
                                admin_name = admin_data[0]
                    
                    logger.info(f"Kullanıcı bilgileri Telegram API'den alındı: {admin_username}")
                except Exception as e:
                    logger.error(f"Telegram API'den kullanıcı bilgileri alma hatası: {str(e)}")
            except Exception as e:
                logger.error(f"Kullanıcı bilgisi alma hatası: {str(e)}")
            
            # API isteği gönder
            response = requests.get(url, headers=headers)
            
            # Yanıtı kontrol et
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Ödeme durumu: {data}")
                
                # Ödeme durumunu al
                payment_status = data.get("payment_status")
                
                # Ödeme durumu değiştiyse bildirim gönder
                if payment_status in ["confirmed", "finished"]:
                    # Bildirim gönder (hata olsa bile devam et)
                    try:
                        payment_data = {
                            "payment_status": payment_status,
                            "payment_id": payment_id,
                            "price_amount": data.get("price_amount"),
                            "price_currency": data.get("price_currency"),
                            "pay_amount": data.get("pay_amount"),
                            "pay_currency": data.get("pay_currency", "USDTTRC20"),
                            "order_description": f"bakiye_{admin_id}",
                            "admin_id": admin_id,
                            "admin_name": admin_name,
                            "admin_username": admin_username
                        }
                        await send_payment_notification(payment_data)
                    except Exception as e:
                        logger.error(f"Bildirim gönderme hatası (önemsiz): {str(e)}")
                    
                    # Bakiyeyi güncelle
                    amount_tl = float(data.get("price_amount"))
                    
                    # TL miktarını kullanım hakkına çevir (10 TL = 1 kullanım hakkı)
                    usage_rights = amount_tl / 10.0
                    
                    success = await self.db.Bakiye_ekle(admin_id, usage_rights)
                    
                    if success:
                        logger.info(f"Bakiye başarıyla güncellendi: Admin ID: {admin_id}, Admin: {admin_name}, Miktar: {amount_tl}₺, Kullanım Hakkı: {usage_rights}")
                        
                        # Kullanıcıya ödeme onaylandı bilgisi gönder
                        try:
                            from telegram import Bot
                            
                            # Bot oluştur
                            bot = Bot(token=TOKEN)
                            
                            # Kullanıcıya bildirim gönder
                            await bot.send_message(
                                chat_id=admin_id,
                                text=(
                                    f"✅ Ödemeniz onaylandı ve hesabınıza yüklendi!\n\n"
                                    f"💰 Yüklenen Tutar: {amount_tl}₺\n"
                                    f"🔢 Eklenen Kullanım Hakkı: {usage_rights}\n\n"
                                    f"🚀 Artık OttoExcel Bot'un tüm özelliklerini kullanabilirsiniz!\n\n"
                                    f"📋 Kullanabileceğiniz tüm komutları görmek için /yardim yazabilirsiniz.\n\n"
                                    f"🙏 OttoExcel Bot'u tercih ettiğiniz için teşekkür ederiz!"
                                )
                            )
                            logger.info(f"Ödeme onay bildirimi kullanıcıya gönderildi: {admin_id}")
                        except Exception as e:
                            logger.error(f"Kullanıcıya bildirim gönderilirken hata oluştu: {str(e)}")
                        
                        return True
                    else:
                        logger.error(f"Bakiye güncellenirken hata oluştu: Admin ID: {admin_id}, Admin: {admin_name}, Miktar: {amount_tl}₺, Kullanım Hakkı: {usage_rights}")
                        return False
                
                return True
            else:
                logger.error(f"Ödeme durumu kontrol hatası: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Ödeme durumu kontrol hatası: {str(e)}")
            return False 