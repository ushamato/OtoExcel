from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from .admin_handlers import AdminHandlers
from .user_handlers import UserHandlers, WAITING_AMOUNT
from .form_handlers import (
    FormHandlers, 
    WAITING_FORM_FIELDS,
    WAITING_CONFIRMATION
)
from bot.database.db_manager import DatabaseManager

def setup_handlers(app: Application):
    db_manager = DatabaseManager()
    admin_handlers = AdminHandlers(db_manager)
    user_handlers = UserHandlers()
    form_handlers = FormHandlers()

    # Form ekleme conversation handler'ı
    form_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('formekle', form_handlers.add_application)],
        states={
            WAITING_FORM_FIELDS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_handlers.save_form_fields)
            ]
        },
        fallbacks=[CommandHandler('iptal', form_handlers.cancel)],
        allow_reentry=True,
        name="form_add"
    )

    # Form veri girişi conversation handler'ı
    form_data_handler = ConversationHandler(
        entry_points=[
            CommandHandler('form', form_handlers.handle_form_command)
        ],
        states={
            WAITING_FORM_FIELDS: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, 
                    form_handlers.handle_form_command
                )
            ]
        },
        fallbacks=[
            CommandHandler('iptal', form_handlers.cancel)
        ],
        allow_reentry=True,
        name="form_data"
    )

    # Bakiye yükleme conversation handler'ı
    load_credits_handler = ConversationHandler(
        entry_points=[CommandHandler('bakiyeyukle', user_handlers.load_credits)],
        states={
            WAITING_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, user_handlers.process_amount)
            ]
        },
        fallbacks=[CommandHandler('iptal', user_handlers.cancel_load_credits)],
        allow_reentry=True,
        name="load_credits"
    )

    # Önce conversation handler'ları ekle
    app.add_handler(form_conv_handler)
    app.add_handler(form_data_handler)
    app.add_handler(load_credits_handler)

    # Sonra diğer handler'ları ekle
    app.add_handler(CommandHandler(['start', 'baslat'], user_handlers.start))
    app.add_handler(CommandHandler(['help', 'yardim'], user_handlers.help))
    app.add_handler(CommandHandler('chatid', user_handlers.chatid))
    
    # Bakiye komutları
    app.add_handler(CommandHandler('bakiyeekle', admin_handlers.add_credits))
    app.add_handler(CommandHandler('bakiyesil', admin_handlers.remove_credits))
    app.add_handler(CommandHandler('bakiye', user_handlers.get_balance))

    # Admin yönetim komutları
    app.add_handler(CommandHandler('adminekle', admin_handlers.add_admin))
    app.add_handler(CommandHandler('adminsil', admin_handlers.remove_admin))
    app.add_handler(CommandHandler('adminler', admin_handlers.list_admins))
    app.add_handler(CommandHandler('gruplar', user_handlers.list_groups))
    
    # Grup yönetim komutları
    app.add_handler(CommandHandler('grupekle', user_handlers.add_group))
    app.add_handler(CommandHandler('grupsil', user_handlers.remove_group))

    # Form komutları
    app.add_handler(CommandHandler('form', form_handlers.handle_form_command))
    app.add_handler(CommandHandler('formlar', form_handlers.list_forms))
    app.add_handler(CommandHandler('formekle', form_handlers.add_application))
    app.add_handler(CommandHandler('formsil', form_handlers.delete_form))
    app.add_handler(CommandHandler('rapor', form_handlers.get_report)) 