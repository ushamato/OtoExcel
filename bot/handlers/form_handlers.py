from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from bot.config import logger, SUPER_ADMIN_ID
from bot.utils.decorators import admin_required
from bot.database.db_manager import DatabaseManager
from functools import wraps
import re
from sqlalchemy import text

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

# Form durumları
WAITING_FORM_FIELDS = 1
WAITING_CONFIRMATION = 2

class FormHandlers:
    """Form işlemleri için handler sınıfı"""
    
    def __init__(self):
        """Initialize the FormHandlers class"""
        self.db = DatabaseManager()
        self.engine = self.db.engine
        # Genel mail formatı için regex pattern - daha sıkı kontrol
        self.mail_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        # Sadece mail adresi alanları için anahtar kelimeler - türkçe karakter dönüşümleri dahil
        self.mail_keywords = [
            'mail', 'email', 'e-mail', 'e-posta', 'eposta', 
            'maıl', 'emaıl', 'e-maıl', 'maıl adres', 'email adres',
            'mail adresi', 'email adresi', 'e-posta adresi',
            'mail adres', 'email adres', 'e-mail adres',
            'elektronik posta', 'elektronık posta'
        ]

    @authorized_group_required
    @admin_required
    async def add_application(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Form ekleme başlangıcı"""
        try:
            args = context.args
            if not args:
                await update.message.reply_text(
                    "📝 Doğru Kullanım:\n"
                    "/formekle FormAdı\n\n"
                    "Örnek:\n"
                    "/formekle yahoo"
                )
                return ConversationHandler.END

            form_name = args[0].lower()
            user_id = update.effective_user.id
            
            # Form zaten var mı kontrol et (sadece bu admin için)
            existing_form = await self.db.get_form(form_name, user_id)
            if existing_form:
                # Form zaten varsa, veri girişi için yönlendir
                await update.message.reply_text(
                    f"📝 '{form_name}' formu zaten mevcut!\n\n"
                    f"Veri girişi yapmak için /form {form_name} komutunu kullanabilirsiniz."
                )
                return ConversationHandler.END
            
            # Form adını context'e kaydet
            context.user_data['form_name'] = form_name

            # Form adını onayla ve alan girişine geç
            await update.message.reply_text(
                f"✅ Form adı: {form_name}\n\n"
                "2️⃣ Form alanlarını belirleyin.\n"
                "❗️ Her alanı yeni bir satıra yazın.\n"
                "📋 Alanların sırası önemlidir, kullanıcılar bu sırayla doldurur.\n\n"
                "Örnek:\n"
                "Ad Soyad\n"
                "Telefon\n"
                "Email"
            )
            return WAITING_FORM_FIELDS

        except Exception as e:
            logger.error(f"Form ekleme başlangıç hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")
            return ConversationHandler.END

    @authorized_group_required
    @admin_required
    async def save_form_fields(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Form alanlarını kaydet ve formu oluştur"""
        try:
            # Alanları satır satır ayır
            fields_text = update.message.text.strip()
            fields = [field.strip() for field in fields_text.split('\n') if field.strip()]
            
            if not fields:
                await update.message.reply_text(
                    "⛔️ En az bir alan girmelisiniz!\n\n"
                    "❗️ Her alanı yeni bir satıra yazın."
                )
                return WAITING_FORM_FIELDS
            
            # Form bilgilerini al
            form_name = context.user_data.get('form_name')
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            
            if not form_name:
                await update.message.reply_text("⛔️ Form adı bulunamadı! Lütfen tekrar deneyin.")
                return ConversationHandler.END
            
            # Formu veritabanına ekle - chat_id'yi group_id olarak kullan
            success = await self.db.add_form(form_name, fields, user_id, chat_id)
            
            if success:
                success_message = (
                    f"✅ Form başarıyla oluşturuldu!\n\n"
                    f"📝 Form Adı: {form_name}\n\n"
                    f"ℹ️ Artık \"/form {form_name}\" komutuyla Excel'e veri girişi yapabilirsiniz.\n\n"
                    f"📋 Form alanlarını görmek için /formlar komutunu kullanabilirsiniz."
                )
                
                await update.message.reply_text(success_message)
            else:
                await update.message.reply_text("⛔️ Form oluşturulurken bir hata oluştu!")
            
            # Kullanıcı verilerini temizle
            context.user_data.clear()
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Form alanları kaydetme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")
            context.user_data.clear()
            return ConversationHandler.END

    @authorized_group_required
    @admin_required
    async def handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Form onayını işle"""
        try:
            user_response = update.message.text.strip().lower()
            
            if user_response == "evet":
                # Form bilgilerini al
                form_name = context.user_data.get('form_name')
                fields = context.user_data.get('form_fields')
                user_id = update.effective_user.id
                
                if not form_name or not fields:
                    await update.message.reply_text("⛔️ Form bilgileri eksik! Lütfen tekrar deneyin.")
                    return ConversationHandler.END
                
                # Formu veritabanına ekle
                success = await self.db.add_form(form_name, fields, user_id)
                
                if success:
                    await update.message.reply_text(f"✅ Form başarıyla oluşturuldu!")
                else:
                    await update.message.reply_text("⛔️ Form oluşturulurken bir hata oluştu!")
                
                # Kullanıcı verilerini temizle
                context.user_data.clear()
                return ConversationHandler.END
            else:
                # Kullanıcı onaylamadı, form alanlarını tekrar girmesini iste
                await update.message.reply_text(
                    "🔄 Form alanlarını tekrar girin:\n\n"
                    "❗️ Her alanı yeni bir satıra yazın.\n"
                    "📋 Alanların sırası önemlidir, kullanıcılar bu sırayla doldurur.\n\n"
                    "Örnek:\n"
                    "Ad Soyad\n"
                    "Telefon\n"
                    "Email"
                )
                return WAITING_FORM_FIELDS
                
        except Exception as e:
            logger.error(f"Form onaylama hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")
            context.user_data.clear()
            return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """İptal komutu"""
        context.user_data.clear()
        await update.message.reply_text(
            "⛔️ Form işlemi iptal edildi.\n"
            "Mevcut formları görmek için /formlar komutunu kullanabilirsiniz."
        )
        return ConversationHandler.END

    async def validate_mail(self, field: str, value: str) -> tuple[bool, str]:
        """Mail adresini doğrula"""
        # Alan adını temizle ve küçük harfe çevir
        field_lower = field.lower()
        
        # Sadece MAİL kelimesi geçiyorsa mail alanıdır (çok basit ve doğrudan kontrol)
        if 'mail' in field_lower or 'maıl' in field_lower or 'e-mail' in field_lower or 'email' in field_lower or 'e-posta' in field_lower:
            logger.info(f"Mail alanı tespit edildi: '{field}'")
            
            # Mail formatını kontrol et - @ işareti ve domain kontrolü (çok basit kontrol)
            if not '@' in value or not '.' in value.split('@')[-1]:
                logger.info(f"Geçersiz mail formatı: '{value}' - @ veya domain eksik")
                return False, (
                    f"⛔️ '{field}' için geçerli bir mail adresi girin!\n\n"
                    "📧 Örnek: kullanici@gmail.com\n\n"
                    "✉️ Mail adresi '@' işareti ve '.com', '.net' gibi bir uzantı içermelidir."
                )
            
        return True, ""

    @authorized_group_required
    @admin_required
    async def handle_form_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Form komutunu işle"""
        try:
            args = context.args
            if not args:
                await update.message.reply_text(
                    "Örnek: /form yahoo\n"
                    "veya\n"
                    "/form yahoo\n"
                    "değer1\n"
                    "değer2\n"
                    "değer3"
                )
                return

            form_name = args[0].lower()
            group_id = update.effective_chat.id
            user_id = update.effective_user.id
            
            # Formun bilgilerini al
            form = await self.db.get_form(form_name)
            
            if not form:
                await update.message.reply_text(
                    f"⛔️ '{form_name}' adında bir form bulunamadı!\n"
                    "Mevcut formları görmek için /formlar komutunu kullanın."
                )
                return

            # Eğer komutla birlikte veriler gönderildiyse
            message_text = update.message.text.strip()
            if '\n' in message_text:
                # Komut ve form adını çıkar, verileri al
                data_lines = message_text.split('\n')[1:]  # İlk satırı (/form form_adi) atla
                
                # Veri sayısı kontrolü
                if len(data_lines) != len(form['fields']):
                    missing_fields = []
                    extra_fields = []
                    
                    if len(data_lines) < len(form['fields']):
                        # Eksik alanları bul
                        missing_fields = form['fields'][len(data_lines):]
                        missing_list = "\n".join(f"• {field}" for field in missing_fields)
                        await update.message.reply_text(
                            f"⛔️ Eksik veri girdiniz!\n\n"
                            f"Eksik Alanlar:\n"
                            f"{missing_list}\n\n"
                            f"❗️ Lütfen tüm bilgileri eksiksiz girin."
                        )
                    else:
                        # Fazla veri girilmiş
                        extra_count = len(data_lines) - len(form['fields'])
                        await update.message.reply_text(
                            f"⛔️ {extra_count} adet fazla veri girdiniz!\n\n"
                            f"Bu form için gerekli alanlar:\n\n" +
                            "\n".join(f"• {field}" for field in form['fields'])
                        )
                    return

                # Her bir alanı kontrol et
                mail_value = None
                mail_field = None
                
                for i, field in enumerate(form['fields']):
                    value = data_lines[i].strip()
                    
                    # Türkçe karakterleri normalize et ve küçük harfe çevir
                    field_normalized = field.lower().replace('İ', 'i').replace('I', 'ı')
                    
                    # Mail alanını algılama - büyük/küçük harf ve Türkçe karakterlerden bağımsız
                    if any(keyword in field_normalized for keyword in ['mail', 'email', 'e-mail', 'eposta', 'e-posta']) or \
                       'mail' in field.lower() or 'maıl' in field.lower() or \
                       'MAIL' in field or 'MAİL' in field or 'EMAIL' in field or 'EMAİL' in field or \
                       'EPOSTA' in field or 'E-POSTA' in field:
                        # Mail şifresi alanını atla
                        if not any(keyword in field.lower() for keyword in ['şifre', 'sifre', 'password', 'parola']):
                            logger.info(f"Mail alanı tespit edildi: '{field}'")
                            mail_value = value
                            mail_field = field
                
                # Mail alanı varsa ve değer geçerli mail değilse uyarı ver
                if mail_value:
                    # Mail formatını kontrol et (basit kontrol)
                    if not '@' in mail_value or not '.' in mail_value.split('@')[-1]:
                        logger.info(f"Geçersiz mail formatı: '{mail_value}' - Alan: '{mail_field}'")
                        await update.message.reply_text(
                            f"⛔️ '{mail_field}' için geçerli bir mail adresi girin!\n\n"
                            "📧 Örnek: kullanici@gmail.com\n\n"
                            "✉️ Mail adresi '@' işareti ve '.com', '.net' gibi bir uzantı içermelidir."
                        )
                        return

                # Verileri kaydet
                form_data = "\n".join(data_lines)
                
                # Form için doğru grup ID'sini al
                with self.engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT group_id, created_by FROM forms 
                        WHERE form_name = :form_name
                        LIMIT 1
                    """), {"form_name": form_name})
                    row = result.fetchone()
                    if row:
                        form_group_id = row[0]
                        form_admin_id = row[1]
                    else:
                        logger.error(f"Form grup ID'si bulunamadı: {form_name}")
                        await update.message.reply_text("⛔️ Form bilgisi alınırken bir hata oluştu!")
                        return
                
                # Adminin bakiyesini kontrol et
                has_credits = await self.check_and_deduct_admin_credits(form_admin_id, update.effective_chat.id)
                
                # Eğer bakiye yetersizse uyarı ver ve işlemi durdur
                if not has_credits:
                    await update.message.reply_text(
                        "⛔️ Bu form için yeterli kullanım hakkı bulunmuyor!\n\n"
                        "Form sahibi adminin bakiyesi yetersiz. Lütfen admin ile iletişime geçin."
                    )
                    return
                
                # Mükerrer kayıt kontrolü
                is_duplicate = await self.db.check_duplicate_submission(
                    form_name=form_name,
                    group_id=form_group_id,
                    data=form_data
                )
                
                if is_duplicate:
                    await update.message.reply_text(
                        "⛔️ Bu form verisi excel tablosunda mevcut!"
                    )
                    return

                submission_id = await self.db.save_form_data(
                    form_name=form_name,
                    group_id=form_group_id,
                    user_id=update.effective_user.id,
                    chat_id=update.effective_chat.id,
                    data=form_data
                )

                if submission_id:
                    # Güncel admin bakiyesini al
                    admin_balance = await self.db.bakiye_getir(form_admin_id)
                    
                    # İsim soyisim bilgisini bul
                    name_surname = None
                    data_lines = form_data.split('\n')
                    
                    # Form alanlarını al
                    form_info = await self.db.get_form(form_name)
                    if form_info and form_info['fields']:
                        fields = form_info['fields']
                        
                        # İsim Soyisim, Ad Soyad, Adı Soyadı gibi alanları ara
                        name_field_keywords = ['isim soyisim', 'ad soyad', 'adı soyadı', 'ad ve soyad']
                        
                        for i, field in enumerate(fields):
                            if i < len(data_lines) and any(keyword in field.lower() for keyword in name_field_keywords):
                                name_surname = data_lines[i]
                                break
                        
                        # Eğer bulunamadıysa ve verinin ilk satırı genellikle isim-soyisim ise
                        if not name_surname and len(data_lines) > 0:
                            name_surname = data_lines[0]  # İlk satırı isim-soyisim olarak kullan
                    
                    # Başarı mesajını hazırla
                    success_message = f"✅ #{submission_id} Numaralı {form_name.capitalize()} Hesabı Excele işlendi. ✅\n"
                    
                    # İsim-Soyisim bilgisi varsa ekle
                    if name_surname:
                        success_message += f"{name_surname}\n"
                    
                    success_message += "\n📝 Yeni veri girişi için:\n"
                    success_message += f"/form {form_name}"
                    
                    await update.message.reply_text(success_message)
                else:
                    await update.message.reply_text("⛔️ Veriler kaydedilirken bir hata oluştu!")
                
                return

            # Eğer sadece komut gönderildiyse form alanlarını göster
            field_list = "\n".join(f"{i+1}. {field}: " for i, field in enumerate(form['fields']))
            
            await update.message.reply_text(
                f"📝 '{form_name}' Formu Veri Girişi\n\n"
                "Lütfen form verilerini aşağıdaki formatta girin:\n\n"
                f"{field_list}\n\n"
                "❗️ ÖNEMLİ NOT: Bilgileri gönderirken sadece bilgileri sırasıyla yazmanız yeterlidir.\n"
                "Başına numara (1., 2., 3.) eklemeyin.\n\n"
                "❓ İptal etmek için /iptal yazabilirsiniz."
            )
            
            # Form bilgilerini context'e kaydet
            context.user_data['current_form'] = form_name
            context.user_data['current_group_id'] = group_id
            return WAITING_FORM_FIELDS

        except Exception as e:
            logger.error(f"Form komut hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")
            return ConversationHandler.END 

    async def check_and_deduct_admin_credits(self, admin_id: int, chat_id: int) -> bool:
        """Admin bakiyesini kontrol et ve form gönderimi için Bakiye düş"""
        try:
            # Sabit form gönderim ücreti (1 kullanım hakkı)
            FORM_SUBMISSION_COST = 1.0
            
            # Admin bakiyesini kontrol et
            admin_balance = await self.db.bakiye_getir(admin_id)
            
            # Bakiye yetersizse False döndür
            if admin_balance < FORM_SUBMISSION_COST:
                return False
                
            # Bakiye yeterliyse Bakiyeyi düş
            success = await self.db.Bakiye_sil(admin_id, FORM_SUBMISSION_COST)
            return success
        except Exception as e:
            logger.error(f"Bakiye kontrolü hatası: {str(e)}")
            return False 