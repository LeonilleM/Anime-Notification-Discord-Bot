# Run: docker build -t anime-bot . && docker run --env-file .env anime-bot
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Mount config.json or .env at runtime, or rely on files copied from the build context.
CMD ["python", "DiscordBot.py"]
