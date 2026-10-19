# BlueSky Bot Docker Image
# ========================
#
# Secrets: do NOT bake credentials via ARG/ENV or COPY.
# Rely on .dockerignore so nested etc/**/.env, opt/**/session.json, etc. never
# enter the build context. At runtime pass config via mounts / env-file, e.g.:
#   docker run --env-file /path/to/.env \
#     -v /path/to/session.json:/app/session.json:ro \
#     bluesky-bot
#

FROM python:3.11-slim

# Метаданные
LABEL maintainer="BlueSky Bot Team"
LABEL description="Automated BlueSky Bot with AI content generation"
LABEL version="2.1"

# Обновляем систему и устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Создаем пользователя для безопасности
RUN groupadd -r botuser && useradd -r -g botuser botuser

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости (слой кэша)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем исходный код (secrets excluded by .dockerignore — no ARG/ENV secrets)
COPY . .

# Создаем директории для данных и логов
RUN mkdir -p /app/data /app/logs && \
    chown -R botuser:botuser /app

# Переключаемся на пользователя
USER botuser

# Healthcheck для мониторинга
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python3 -c "import os; exit(0 if os.path.exists('bot.log') else 1)"

# Non-secret runtime defaults only (credentials via --env-file / mounts)
ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO
ENV BLUESKY_COMPLIANT_MODE=true

# Точка входа
CMD ["python3", "bluesky_bot_v2.py"]
