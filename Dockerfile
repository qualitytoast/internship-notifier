# Optional: run InternWatch in a container instead of systemd.
#   docker build -t internwatch .
#   docker run -d --name internwatch --restart unless-stopped --env-file .env -v internwatch-data:/app/data internwatch
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 INTERNWATCH_HOME=/app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e .
COPY config ./config
COPY discovery/results ./discovery/results
VOLUME ["/app/data"]
# Polls every 15 minutes, forever (the same schedule as the systemd timer).
CMD ["internwatch", "daemon"]
