FROM node:22-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=10000 \
    REQUIRE_APP_PASSWORD=true \
    PATH="/opt/nazzelha-venv/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ffmpeg ca-certificates \
    && python3 -m venv /opt/nazzelha-venv \
    && /opt/nazzelha-venv/bin/pip install --no-cache-dir "yt-dlp[default]" \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py /app/app.py
COPY website /app/website
RUN mkdir -p /app/downloads && chmod 755 /app/downloads

EXPOSE 10000
CMD ["/opt/nazzelha-venv/bin/python", "/app/app.py"]
