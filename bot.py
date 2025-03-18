from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import sqlite3
import pandas as pd
from datetime import datetime
import hashlib
import os
from dotenv import load_dotenv

# .env dosyasından değişkenleri yükle
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
SUPER_ADMIN = int(os.getenv('SUPER_ADMIN_ID'))

# Conversation states
WAITING_FORM_FIELDS = 1
COLLECTING_DATA = 2

class FormBot:
    def __init__(self):
        self.db = sqlite3.connect('forms.db')
        self.setup_database()
    
    def setup_database(self):
        cursor = self.db.cursor()
        # Formları saklayacak tablo
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS forms (
                form_name TEXT PRIMARY KEY,
                fields TEXT,
                created_by INTEGER
            )
        ''')
        # Grup Bakiyelerini saklayacak tablo
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_credits (
                group_id INTEGER PRIMARY KEY,
                remaining_credits INTEGER
            )
        ''')
        self.db.commit()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Merhaba! Form oluşturmak için /uygulamaekle komutunu kullanabilirsiniz."
        )

    async def add_application(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await self.is_admin(update.effective_user.id):
            await update.message.reply_text("Bu komutu kullanma yetkiniz yok!")
            return ConversationHandler.END
        
        await update.message.reply_text(
            "Lütfen form adını /formadi şeklinde gönderin\n"
            "Örnek: /yahoo"
        )
        return WAITING_FORM_FIELDS

    async def save_form_fields(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Form alanlarını kaydet
        fields = update.message.text.strip().split('\n')
        form_name = context.user_data.get('current_form')
        
        cursor = self.db.cursor()
        cursor.execute(
            "INSERT INTO forms (form_name, fields, created_by) VALUES (?, ?, ?)",
            (form_name, ','.join(fields), update.effective_user.id)
        )
        self.db.commit()

        await update.message.reply_text(f"{form_name} formu başarıyla oluşturuldu!")
        return ConversationHandler.END

    async def add_credits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != SUPER_ADMIN:
            await update.message.reply_text("Bu komutu sadece süper admin kullanabilir!")
            return

        try:
            _, group_id, credits = update.message.text.split()
            cursor = self.db.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO group_credits (group_id, remaining_credits) VALUES (?, ?)",
                (int(group_id), int(credits))
            )
            self.db.commit()
            await update.message.reply_text(f"Gruba {credits} Bakiye eklendi!")
        except:
            await update.message.reply_text("Hatalı format! Örnek: /Bakiyeekle group_id miktar")

    async def export_excel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Excel raporu oluştur
        pass

def main():
    bot = FormBot()
    application = Application.builder().token(TOKEN).build()
    
    # Handler'ları ekle
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('uygulamaekle', bot.add_application)],
        states={
            WAITING_FORM_FIELDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.save_form_fields)]
        },
        fallbacks=[]
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('start', bot.start))
    application.add_handler(CommandHandler('Bakiyeekle', bot.add_credits))
    
    application.run_polling()

if __name__ == '__main__':
    main() 