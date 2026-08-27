FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Проверка структуры на этапе сборки: если bot/ не на месте,
# билд упадёт здесь с понятным сообщением, а не в рантайме.
RUN echo "--- содержимое /app ---" && ls -R /app | head -50 && \
    test -f /app/bot/main.py || (echo "ОШИБКА: нет /app/bot/main.py — проверь структуру репозитория" && exit 1) && \
    test -f /app/bot/__init__.py || (echo "ОШИБКА: нет /app/bot/__init__.py" && exit 1)

CMD ["python", "-m", "bot.main"]
