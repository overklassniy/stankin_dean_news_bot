# Используем общий base образ
FROM python-base-bots

WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY *.py .
COPY config.json .
COPY images/ ./images/

# Создаём директории для данных и логов (будут монтироваться как volumes)
RUN mkdir -p /app/data /app/logs

# Запуск бота
CMD ["python", "bot.py"]
