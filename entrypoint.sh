#!/bin/bash
set -e

# Otomatik yeniden başlatma döngüsü
while true; do
    echo "Bot başlatılıyor..."
    python -u /app/bot/main.py || true
    echo "Bot çıkış yaptı veya çöktü. 5 saniye içinde yeniden başlatılacak..."
    sleep 5
done 