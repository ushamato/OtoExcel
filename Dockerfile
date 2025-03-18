FROM python:3.11-slim

# Çalışma dizinini ayarla
WORKDIR /app

# PostgreSQL istemci kütüphaneleri için gerekli paketleri kur
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    python3-dev \
    libxml2-dev \
    libxslt-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Önce sadece requirements.txt'yi kopyala
COPY requirements.txt .

# Python paketlerini yükle
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir sqlalchemy==2.0.25 psycopg2-binary==2.9.9 && \
    pip install --no-cache-dir "python-telegram-bot[callback-data]"==20.7 && \
    pip install --no-cache-dir python-dotenv

# Tüm projeyi kopyala
COPY . .

# Entrypoint scriptine execute yetkisi ver
RUN chmod +x /app/entrypoint.sh

# Python path'i ayarla
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Entrypoint script'i çalıştır
CMD ["/app/entrypoint.sh"] 