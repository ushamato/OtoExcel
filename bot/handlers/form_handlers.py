from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from bot.config import logger, SUPER_ADMIN_ID, IMGBB_API_KEY, IMGBB_UPLOAD_URL
from bot.database.db_manager import DatabaseManager
from bot.utils.decorators import super_admin_required, admin_required
from functools import wraps
from sqlalchemy import text
from datetime import datetime
import aiohttp
import base64
from io import BytesIO

def authorized_group_required(func):
    """Komutun sadece yetkili gruplarda çalışmasını sağlayan dekoratör"""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat
        user = update.effective_user
        
        # Süper admin her yerde çalıştırabilir
        if user.id == SUPER_ADMIN_ID:
            return await func(self, update, context, *args, **kwargs)
        
        # Admin mi kontrol et
        is_admin = await self.db.is_admin(user.id)
        if is_admin:
            return await func(self, update, context, *args, **kwargs)
        
        # Özel mesajlarda sadece adminler kullanabilir - yukarıda kontrol edildi
        if chat.type == 'private':
            await update.message.reply_text(
                "⛔️ Bu komutu kullanma yetkiniz yok!"
            )
            return
        
        # Grup yetkili mi kontrol et
        is_authorized = await self.db.is_authorized_group(chat.id)
        if not is_authorized:
            await update.message.reply_text(
                "⛔️ Bu grup yetkili bir admin tarafından eklenmemiş!\n\n"
                "ℹ️ Botun çalışması için bir admin tarafından grubun eklenmesi gerekiyor."
            )
            return
        
        # Yetkili grupta herkes kullanabilir
        return await func(self, update, context, *args, **kwargs)
    return wrapper

# Form durumları
WAITING_FORM_FIELDS = 1
WAITING_CONFIRMATION = 2
WAITING_DEKONT = 3

class FormHandlers:
    """Form işlemleri için handler sınıfı"""
    
    def __init__(self):
        """Initialize the FormHandlers class"""
        self.db = DatabaseManager()
        self.engine = self.db.engine

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
                "⚠️ Form içeriğinde DEKONT bilgisi bulunacaksa en son bilgi olarak GİRİNİZ.\n\n"
                "Örnek:\n"
                "Ad Soyad\n"
                "Telefon\n"
                "Email\n"
                "Dekont\n\n"
                "🚫 İşlemi iptal etmek için 'iptal' yazmanız yeterlidir."
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
            
            # İptal kontrolü
            if fields_text.lower() == "iptal":
                return await self.cancel(update, context)
            
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
            
            if user_response == "iptal":
                return await self.cancel(update, context)
                
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
                    "⚠️ Form içeriğinde DEKONT bilgisi bulunacaksa en son bilgi olarak GİRİNİZ.\n\n"
                    "Örnek:\n"
                    "Ad Soyad\n"
                    "Telefon\n"
                    "Email\n"
                    "Dekont"
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

    @authorized_group_required
    async def handle_form_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Form komutunu işle"""
        try:
            # İptal kontrolü
            if update.message.text and update.message.text.strip().lower() == "iptal":
                return await self.cancel(update, context)
                
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

            # Form alanlarını kontrol et, son alanda "dekont" var mı?
            fields = form['fields']
            has_dekont = False
            if fields and len(fields) > 0:
                last_field = fields[-1].lower()
                has_dekont = "dekont" in last_field

            # Eğer komutla birlikte veriler gönderildiyse
            message_text = update.message.text.strip()
            if '\n' in message_text:
                # Komut ve form adını çıkar, verileri al
                data_lines = message_text.split('\n')[1:]  # İlk satırı (/form form_adi) atla
                
                # Veri sayısı kontrolü
                if len(data_lines) != len(form['fields']):
                    missing_fields = []
                    extra_fields = []
                    
                    # Dekont durumunu kontrol et
                    if has_dekont and len(data_lines) == len(form['fields']) - 1:
                        # Son alan dekont ve kullanıcı form alanlarını eksiksiz göndermiş, dekont hariç
                        # Form verilerini context'e kaydet
                        context.user_data['form_name'] = form_name
                        context.user_data['form_data'] = "\n".join(data_lines)
                        context.user_data['form_group_id'] = group_id
                        
                        # Fotoğraf gönderilmesini iste
                        await update.message.reply_text(
                            "📸 Lütfen dekont görselini gönderin...\n\n"
                            "💳 Görsel JPEG, PNG veya PDF formatında olabilir.\n\n"
                            "🚫 İşlemi iptal etmek için 'iptal' yazmanız yeterlidir."
                        )
                        
                        return WAITING_DEKONT
                    elif len(data_lines) < len(form['fields']):
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

                # Verileri kaydet (dekont olanlar hariç geçici olarak)
                # Eğer dekont alanı varsa ve dekont görüntüsü yoksa, kullanıcıdan iste
                if has_dekont and not context.user_data.get('dekont_url'):
                    # Form verilerini context'e kaydet
                    context.user_data['form_name'] = form_name
                    context.user_data['form_data'] = "\n".join(data_lines)
                    context.user_data['form_group_id'] = group_id
                    
                    # Fotoğraf gönderilmesini iste
                    await update.message.reply_text(
                        "📸 Lütfen dekont görselini gönderin...\n\n"
                        "💳 Görsel JPEG, PNG veya PDF formatında olabilir.\n\n"
                        "🚫 İşlemi iptal etmek için 'iptal' yazmanız yeterlidir."
                    )
                    
                    return WAITING_DEKONT
                
                # Dekont yoksa normal işleme devam et
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

                # Dekont URL'i varsa form datasına ekle
                if context.user_data.get('dekont_url'):
                    form_data = form_data + "\n" + context.user_data.get('dekont_url')
                
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
                    
                    # Dekont eklendiğine dair bilgi
                    if context.user_data.get('dekont_url'):
                        success_message += "📸 Dekont görüntüsü başarıyla eklendi.\n"
                        
                    # Context'ten dekont bilgisini temizle
                    if 'dekont_url' in context.user_data:
                        del context.user_data['dekont_url']
                    
                    success_message += "\n📝 Yeni veri girişi için:\n"
                    success_message += f"/form {form_name}"
                    
                    await update.message.reply_text(success_message)
                else:
                    await update.message.reply_text("⛔️ Veriler kaydedilirken bir hata oluştu!")
                
                return

            # Eğer sadece komut gönderildiyse form alanlarını göster
            field_list = "\n".join(f"{i+1}. {field}: " for i, field in enumerate(form['fields']))
            
            dekont_info = ""
            if has_dekont:
                dekont_info = "\n\n📸 SON ADIM olarak dekont görüntüsü istenecektir."
                dekont_info += "\n❗️ Dekont hariç tüm alanları doldurun, sonraki adımda dekont isteyeceğim."
            
            await update.message.reply_text(
                f"📝 '{form_name}' Formu Veri Girişi\n\n"
                "Lütfen form verilerini aşağıdaki formatta girin:\n\n"
                f"{field_list}\n\n"
                "❗️ ÖNEMLİ NOT: Bilgileri gönderirken sadece bilgileri sırasıyla yazmanız yeterlidir.\n"
                "Başına numara (1., 2., 3.) eklemeyin." + dekont_info + "\n\n"
                "🚫 İşlemi iptal etmek için 'iptal' yazmanız yeterlidir."
            )
            
            # Form bilgilerini context'e kaydet
            context.user_data['current_form'] = form_name
            context.user_data['current_group_id'] = group_id
            context.user_data['has_dekont'] = has_dekont
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

    @admin_required
    async def delete_form(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Form sil"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "⛔️ Form adı belirtmelisiniz!\n\n"
                    "Örnek:\n"
                    "/formsil yahoo"
                )
                return
            
            form_name = context.args[0]
            chat = update.effective_chat
            
            # Formu sil
            success = await self.db.delete_form(form_name, chat.id)
            
            if success:
                await update.message.reply_text(f"✅ '{form_name}' formu başarıyla silindi.")
            else:
                await update.message.reply_text(
                    "⛔️ Form silinemedi!\n\n"
                    "Olası nedenler:\n"
                    "• Form bulunamadı\n"
                    "• Form size ait değil\n"
                    "• Veritabanı hatası"
                )
                
        except Exception as e:
            logger.error(f"Form silme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!") 

    @authorized_group_required
    async def list_forms(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Formları listele"""
        try:
            chat = update.effective_chat
            user = update.effective_user
            is_super_admin = user.id == SUPER_ADMIN_ID
            
            # Formları getir - adminin tüm gruplarındaki formları getir
            forms = await self.db.get_forms_by_group(chat.id, user.id)
            
            if forms and len(forms) > 0:
                message = "📋 Mevcut Formlar:\n\n"
                for form in forms:
                    message += f"📝 {form['form_name']}\n"
                    fields = form['fields'].split(',')
                    message += "🔹 Alanlar: " + ", ".join(fields) + "\n\n"
            else:
                message = "⛔️ Henüz hiç form bulunmamaktadır."
            
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
                    "/rapor form adı\n\n"
                    "Örnek:\n"
                    "/rapor yahoo\n\n"
                    "📅 Belirli bir tarih aralığı için rapor almak isterseniz:\n"
                    "/rapor form adı GG.AA.YYYY GG.AA.YYYY\n\n"
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
                # Form var mı kontrol et
                form = await self.db.get_form(form_name)
                if not form:
                    await update.message.reply_text(
                        f"⛔️ '{form_name}' adında bir form bulunamadı!\n\n"
                        "📋 Mevcut formları görmek için /formlar komutunu kullanın."
                    )
                    return
                
                # Form varsa ama veri yoksa
                if start_date and end_date:
                    await update.message.reply_text(
                        f"⛔️ Belirtilen tarih aralığında veri bulunamadı!\n\n"
                        f"📅 {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')} "
                        f"tarihleri arasında '{form_name}' formuna ait veri girişi yapılmamış."
                    )
                else:
                    await update.message.reply_text(
                        f"⛔️ Bugün için veri bulunamadı!\n\n"
                        f"📅 '{form_name}' formuna bugün hiç veri girişi yapılmamış.\n\n"
                        "💡 Belirli bir tarih aralığı için rapor almak isterseniz:\n"
                        "/rapor form_adi GG.AA.YYYY GG.AA.YYYY\n\n"
                        "Örnek:\n"
                        "/rapor yahoo 01.03.2025 18.03.2025"
                    )
            
        except Exception as e:
            logger.error(f"Rapor oluşturma hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    async def upload_image_to_imgbb(self, photo_file):
        """ImgBB API'sine görsel yükle ve URL'i döndür"""
        try:
            # Fotoğrafı indir
            photo_data = await photo_file.download_as_bytearray()
            
            # Base64 kodlaması yap
            base64_image = base64.b64encode(photo_data).decode('utf-8')
            
            # ImgBB API'sine gönder
            async with aiohttp.ClientSession() as session:
                params = {
                    'key': IMGBB_API_KEY,
                    'image': base64_image
                }
                
                async with session.post(IMGBB_UPLOAD_URL, data=params) as response:
                    if response.status != 200:
                        logger.error(f"ImgBB API hatası: {response.status}")
                        return None
                    
                    # Yanıtı JSON olarak al
                    data = await response.json()
                    
                    if not data.get('success'):
                        logger.error(f"ImgBB API yanıt hatası: {data}")
                        return None
                    
                    # URL'i döndür
                    return data['data']['url']
                    
        except Exception as e:
            logger.error(f"Görsel yükleme hatası: {str(e)}")
            return None

    async def handle_dekont(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Dekont görüntüsünü işle"""
        try:
            # Kullanıcı iptal ettiyse
            if update.message.text and update.message.text.lower() == 'iptal':
                return await self.cancel(update, context)
            
            # Fotoğraf veya doküman kontrolü
            photo = None
            if update.message.photo:
                # En büyük boyutlu fotoğrafı al
                photo = update.message.photo[-1]
            elif update.message.document:
                # Doküman formatını kontrol et (jpg, png, pdf)
                mime_type = update.message.document.mime_type
                if mime_type and mime_type.startswith(('image/', 'application/pdf')):
                    photo = update.message.document
                else:
                    await update.message.reply_text(
                        "⛔️ Lütfen geçerli bir görsel formatı gönderin (JPEG, PNG, PDF).\n\n"
                        "🚫 İşlemi iptal etmek için 'iptal' yazmanız yeterlidir."
                    )
                    return WAITING_DEKONT
            
            if not photo:
                await update.message.reply_text(
                    "⛔️ Lütfen bir görsel gönderin.\n\n"
                    "💳 Dekont görüntüsü JPEG, PNG veya PDF formatında olmalıdır.\n\n"
                    "🚫 İşlemi iptal etmek için 'iptal' yazmanız yeterlidir."
                )
                return WAITING_DEKONT
            
            # Yükleniyor mesajı
            processing_message = await update.message.reply_text("⏳ Dekont görüntüsü yükleniyor...")
            
            # Fotoğrafı ImgBB'ye yükle
            photo_file = await photo.get_file()
            image_url = await self.upload_image_to_imgbb(photo_file)
            
            # Yükleme mesajını sil
            await processing_message.delete()
            
            if not image_url:
                await update.message.reply_text(
                    "⛔️ Dekont görüntüsü yüklenirken bir hata oluştu. Lütfen tekrar deneyin.\n\n"
                    "🚫 İşlemi iptal etmek için 'iptal' yazmanız yeterlidir."
                )
                return WAITING_DEKONT
            
            # URL'i context'e kaydet
            context.user_data['dekont_url'] = image_url
            
            # Form bilgilerini al
            form_name = context.user_data.get('form_name')
            form_data = context.user_data.get('form_data')
            form_group_id = context.user_data.get('form_group_id')
            
            if not form_name or not form_data or not form_group_id:
                await update.message.reply_text("⛔️ Form bilgileri eksik! Lütfen tekrar deneyin.")
                context.user_data.clear()
                return ConversationHandler.END
            
            # Form için admin ID'sini al
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT created_by FROM forms 
                    WHERE form_name = :form_name
                    LIMIT 1
                """), {"form_name": form_name})
                row = result.fetchone()
                if row:
                    form_admin_id = row[0]
                else:
                    logger.error(f"Form admin ID'si bulunamadı: {form_name}")
                    await update.message.reply_text("⛔️ Form bilgisi alınırken bir hata oluştu!")
                    context.user_data.clear()
                    return ConversationHandler.END
                
            # Adminin bakiyesini kontrol et
            has_credits = await self.check_and_deduct_admin_credits(form_admin_id, update.effective_chat.id)
            
            # Eğer bakiye yetersizse uyarı ver ve işlemi durdur
            if not has_credits:
                await update.message.reply_text(
                    "⛔️ Bu form için yeterli kullanım hakkı bulunmuyor!\n\n"
                    "Form sahibi adminin bakiyesi yetersiz. Lütfen admin ile iletişime geçin."
                )
                context.user_data.clear()
                return ConversationHandler.END
            
            # Form datasına dekont URL'ini ekle
            form_data_with_url = form_data + "\n" + image_url
            
            # Mükerrer kayıt kontrolü
            is_duplicate = await self.db.check_duplicate_submission(
                form_name=form_name,
                group_id=form_group_id,
                data=form_data_with_url
            )
            
            if is_duplicate:
                await update.message.reply_text(
                    "⛔️ Bu form verisi excel tablosunda mevcut!"
                )
                context.user_data.clear()
                return ConversationHandler.END
            
            # Form verisini kaydet
            submission_id = await self.db.save_form_data(
                form_name=form_name,
                group_id=form_group_id,
                user_id=update.effective_user.id,
                chat_id=update.effective_chat.id,
                data=form_data_with_url
            )
            
            if submission_id:
                # Başarı mesajını hazırla
                success_message = f"✅ #{submission_id} Numaralı {form_name.capitalize()} Hesabı Excele işlendi. ✅\n"
                
                # İsim soyisim bilgisini bul
                name_surname = None
                data_lines = form_data.split('\n')
                if data_lines and len(data_lines) > 0:
                    name_surname = data_lines[0]  # İlk satırı isim-soyisim olarak kullan
                
                # İsim-Soyisim bilgisi varsa ekle
                if name_surname:
                    success_message += f"{name_surname}\n"
                
                success_message += "📸 Dekont görüntüsü başarıyla eklendi.\n\n"
                success_message += "📝 Yeni veri girişi için:\n"
                success_message += f"/form {form_name}"
                
                await update.message.reply_text(success_message)
            else:
                await update.message.reply_text("⛔️ Veriler kaydedilirken bir hata oluştu!")
            
            # Context'i temizle
            context.user_data.clear()
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"Dekont işleme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")
            context.user_data.clear()
            return ConversationHandler.END
