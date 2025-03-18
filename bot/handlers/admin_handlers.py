from telegram import Update
from telegram.ext import ContextTypes
from bot.config import SUPER_ADMIN_ID, logger
from bot.database.db_manager import DatabaseManager
from bot.utils.decorators import super_admin_required

class AdminHandlers:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    @super_admin_required
    async def add_credits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admine Bakiye ekle"""
        try:
            # Sadece süper admin bu komutu kullanabilir
            user = update.effective_user
            if user.id != SUPER_ADMIN_ID:
                await update.message.reply_text("⛔️ Bu komutu sadece süper admin kullanabilir!")
                return
            
            # Komut argümanlarını kontrol et
            if not context.args or len(context.args) != 2:
                await update.message.reply_text(
                    "⛔️ Hatalı format!\n\n"
                    "📝 Doğru Kullanım:\n"
                    "/bakiyeekle AdminID Miktar\n\n"
                    "📱 Örnek:\n"
                    "/bakiyeekle 1234567890 100"
                )
                return
            
            # Admin ID ve Bakiye miktarını al
            try:
                admin_id = context.args[0]
                miktar_tl = float(context.args[1])
                
                if miktar_tl <= 0:
                    await update.message.reply_text("⛔️ Bakiye miktarı pozitif bir sayı olmalıdır!")
                    return
            except ValueError:
                await update.message.reply_text("⛔️ Geçersiz miktar! Sayısal bir değer giriniz.")
                return
            
            # Adminin var olup olmadığını kontrol et
            is_admin = await self.db.is_admin(admin_id)
            if not is_admin:
                await update.message.reply_text(f"⛔️ {admin_id} ID'li bir admin bulunamadı!")
                return
            
            # TL miktarını kullanım hakkına çevir (10 TL = 1 kullanım hakkı)
            usage_rights = miktar_tl / 10.0
            
            # Bakiye ekle
            success = await self.db.Bakiye_ekle(admin_id, usage_rights)
            
            if success:
                # Güncel bakiyeyi al
                current_balance = await self.db.bakiye_getir(admin_id)
                
                await update.message.reply_text(
                    f"✅ Admin bakiyesi güncellendi!\n\n"
                    f"👤 Admin ID: {admin_id}\n"
                    f"💰 Eklenen Miktar: {miktar_tl}₺ ({usage_rights} kullanım hakkı)\n"
                    f"💵 Güncel Kullanım Hakkı: {current_balance}"
                )
            else:
                await update.message.reply_text("⛔️ Bakiye eklenirken bir hata oluştu!")
                
        except Exception as e:
            logger.error(f"Bakiye ekleme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    @super_admin_required
    async def remove_credits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Adminden Bakiye sil"""
        try:
            # Sadece süper admin bu komutu kullanabilir
            user = update.effective_user
            if user.id != SUPER_ADMIN_ID:
                await update.message.reply_text("⛔️ Bu komutu sadece süper admin kullanabilir!")
                return
            
            # Komut argümanlarını kontrol et
            if not context.args or len(context.args) != 2:
                await update.message.reply_text(
                    "⛔️ Hatalı format!\n\n"
                    "📝 Doğru Kullanım:\n"
                    "/bakiyesil AdminID KullanımHakkı\n\n"
                    "📱 Örnek:\n"
                    "/bakiyesil 1234567890 50"
                )
                return
            
            # Admin ID ve kullanım hakkı miktarını al
            try:
                admin_id = context.args[0]
                usage_rights = float(context.args[1])
                
                if usage_rights <= 0:
                    await update.message.reply_text("⛔️ Kullanım hakkı miktarı pozitif bir sayı olmalıdır!")
                    return
            except ValueError:
                await update.message.reply_text("⛔️ Geçersiz miktar! Sayısal bir değer giriniz.")
                return
            
            # Adminin var olup olmadığını kontrol et
            is_admin = await self.db.is_admin(admin_id)
            if not is_admin:
                await update.message.reply_text(f"⛔️ {admin_id} ID'li bir admin bulunamadı!")
                return
            
            # Mevcut bakiyeyi kontrol et
            current_balance = await self.db.bakiye_getir(admin_id)
            if current_balance < usage_rights:
                await update.message.reply_text(
                    f"⛔️ Yetersiz kullanım hakkı!\n\n"
                    f"👤 Admin ID: {admin_id}\n"
                    f"💰 Mevcut Kullanım Hakkı: {current_balance}\n"
                    f"💸 Silinmek İstenen: {usage_rights}"
                )
                return
            
            # Bakiye sil
            success = await self.db.Bakiye_sil(admin_id, usage_rights)
            
            if success:
                # Güncel bakiyeyi al
                new_balance = await self.db.bakiye_getir(admin_id)
                
                await update.message.reply_text(
                    f"✅ Admin bakiyesi güncellendi!\n\n"
                    f"👤 Admin ID: {admin_id}\n"
                    f"💰 Silinen Kullanım Hakkı: {usage_rights}\n"
                    f"💵 Güncel Kullanım Hakkı: {new_balance}"
                )
            else:
                await update.message.reply_text("⛔️ Bakiye silinirken bir hata oluştu!")
                
        except Exception as e:
            logger.error(f"Bakiye silme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    @super_admin_required
    async def add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin ekle"""
        try:
            # Sadece süper admin bu komutu kullanabilir
            user = update.effective_user
            if user.id != SUPER_ADMIN_ID:
                await update.message.reply_text("⛔️ Bu komutu sadece süper admin kullanabilir!")
                return
            
            # Komut argümanlarını kontrol et
            if not context.args or len(context.args) < 2:
                await update.message.reply_text(
                    "⛔️ Hatalı format!\n\n"
                    "📝 Doğru Kullanım:\n"
                    "/adminekle AdminİSMİ TelegramID\n\n"
                    "📱 Örnek:\n"
                    "/adminekle Admin 1234567890"
                )
                return
            
            # Admin adı ve User ID'yi al
            admin_name = context.args[0]
            try:
                user_id = int(context.args[1])
                # Stringlerle çalışabilmesi için string'e çevir
                user_id_str = str(user_id)
            except ValueError:
                await update.message.reply_text("⛔️ Geçersiz Telegram ID! Sayısal bir değer giriniz.")
                return
            
            # Admin ekle (await ile çağır ve parametre sırasını düzelt)
            success = await self.db.add_admin(user_id_str, admin_name, str(user.id))
            
            if success:
                await update.message.reply_text(
                    f"✅ Admin başarıyla eklendi!\n\n"
                    f"👤 Admin: {admin_name}\n"
                    f"🆔 Telegram ID: {user_id}"
                )
            else:
                await update.message.reply_text(f"⚠️ {admin_name} ({user_id}) zaten admin!")
                
        except Exception as e:
            logger.error(f"Admin ekleme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    @super_admin_required
    async def remove_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin sil"""
        try:
            # Sadece süper admin bu komutu kullanabilir
            user = update.effective_user
            if user.id != SUPER_ADMIN_ID:
                await update.message.reply_text("⛔️ Bu komutu sadece süper admin kullanabilir!")
                return
            
            # Komut argümanlarını kontrol et
            if not context.args or len(context.args) < 1:
                await update.message.reply_text(
                    "⛔️ Hatalı format!\n\n"
                    "📝 Doğru Kullanım:\n"
                    "/adminsil TelegramID\n\n"
                    "Örnek:\n"
                    "/adminsil 1234567890"
                )
                return
            
            # User ID'yi al
            try:
                user_id = int(context.args[0])
            except ValueError:
                await update.message.reply_text("⛔️ Geçersiz user ID! Sayısal bir değer giriniz.")
                return
            
            # Admin sil
            success = await self.db.remove_admin(user_id)
            
            if success:
                await update.message.reply_text(f"✅ {user_id} ID'li admin silindi!")
            else:
                await update.message.reply_text(f"⚠️ {user_id} ID'li admin bulunamadı!")
                
        except Exception as e:
            logger.error(f"Admin silme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    @super_admin_required
    async def list_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            admins = await self.db.get_all_admins()
            
            if admins and len(admins) > 0:
                message = "👥 Admin Listesi:\n\n"
                for admin in admins:
                    admin_name = admin.get('admin_name', "İsimsiz Admin")
                    message += f"👤 Admin: {admin_name}\n"
                    message += f"🆔 ID: {admin['user_id']}\n"
                    message += f"💰 Bakiye: {admin['remaining_credits']}\n\n"
            else:
                message = "⛔️ Henüz admin bulunmamaktadır."

            await update.message.reply_text(message)

        except Exception as e:
            logger.error(f"Admin listeleme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    @super_admin_required
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Admin komut işlemleri
        pass

    @super_admin_required
    async def grup_ekle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Yeni grup ekle"""
        try:
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
            except ValueError:
                await update.message.reply_text("⛔️ Grup ID sayısal olmalıdır!")
                return

            group_name = " ".join(args[1:])
            success = await self.db.add_group(group_id, group_name)

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

    @super_admin_required
    async def grup_sil(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Grup sil"""
        try:
            args = context.args
            if not args:
                await update.message.reply_text(
                    "⛔️ Hatalı format!\n\n"
                    "📝 Doğru Kullanım:\n"
                    "/grupsil GrupID\n\n"
                    "Örnek:\n"
                    "/grupsil -1234567890"
                )
                return

            try:
                group_id = int(args[0])
            except ValueError:
                await update.message.reply_text("⛔️ Grup ID sayısal olmalıdır!")
                return

            # Grup adını al
            group_name = await self.db.get_group_name(group_id)
            if not group_name:
                await update.message.reply_text("⛔️ Belirtilen ID'ye sahip grup bulunamadı!")
                return

            success = await self.db.remove_group(group_id)
            if success:
                await update.message.reply_text(
                    f"✅ Grup başarıyla silindi!\n\n"
                    f"🏢 Grup: {group_name}\n"
                    f"🆔 ID: {group_id}"
                )
            else:
                await update.message.reply_text("⛔️ Grup silinirken bir hata oluştu!")

        except Exception as e:
            logger.error(f"Grup silme hatası: {str(e)}")
            await update.message.reply_text("⛔️ Bir hata oluştu!")

    # Diğer admin komutları... 