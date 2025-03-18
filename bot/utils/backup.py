import shutil
from datetime import datetime
import os

def backup_database():
    """Veritabanını yedekle"""
    try:
        # Yedek dosya adı oluştur
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f'database/backup/forms_{timestamp}.db'
        
        # Yedekleme klasörünü oluştur
        os.makedirs('database/backup', exist_ok=True)
        
        # Veritabanını kopyala
        shutil.copy2('database/forms.db', backup_file)
        
        return True
    except Exception as e:
        print(f"Yedekleme hatası: {str(e)}")
        return False 