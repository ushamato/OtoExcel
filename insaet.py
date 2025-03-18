#!/usr/bin/env python3
import subprocess
import sys
import time
import os

def run_command(command):
    """Komutu çalıştır ve çıktıyı göster"""
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            shell=True
        )
        
        # Çıktıyı gerçek zamanlı göster
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
        
        return process.poll()
    except Exception as e:
        print(f"⛔️ Hata: {str(e)}")
        return 1

def main():
    print("🔄 Bot yeniden başlatılıyor...")
    
    # Docker compose down
    print("\n📥 Containerlar durduruluyor...")
    if run_command("docker-compose down") != 0:
        print("⛔️ Containerlar durdurulamadı!")
        sys.exit(1)
    
    # Kısa bekle
    time.sleep(2)
    
    # Docker compose up
    print("\n📤 Containerlar başlatılıyor...")
    if run_command("docker-compose up -d --build") != 0:
        print("⛔️ Containerlar başlatılamadı!")
        sys.exit(1)
    
    print("\n✅ Bot başarıyla yeniden başlatıldı!")
    
    # Logları göster
    print("\n📋 Bot logları:")
    run_command("docker-compose logs -f")

if __name__ == "__main__":
    # Scripti çalıştırılabilir yap
    script_path = os.path.abspath(__file__)
    os.chmod(script_path, 0o755)
    main() 