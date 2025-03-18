from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from config import SUPER_ADMIN_ID  # .env'den alınacak süper admin ID'si

def super_admin_required(func):
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != SUPER_ADMIN_ID:
            await update.message.reply_text("⛔️ Bu komutu kullanma yetkiniz yok!")
            return
        return await func(self, update, context, *args, **kwargs)
    return wrapper

def admin_required(func):
    """Admin yetkisi gerektiren komutlar için dekoratör"""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        is_admin = await self.db.is_group_admin(user.id)
        
        if not is_admin and user.id != SUPER_ADMIN_ID:
            await update.message.reply_text("⛔️ Bu komutu kullanma yetkiniz yok!")
            return
            
        return await func(self, update, context, *args, **kwargs)
    return wrapper 