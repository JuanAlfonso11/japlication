FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for lxml / psycopg-style builds (kept minimal for asyncpg + lxml wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# pip/setuptools upgraded too: the base image's copies carry advisories
# (pip-audit), even though the app never calls them at runtime.
RUN pip install --no-cache-dir --upgrade pip setuptools \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Normalized and made executable in the image rather than relying on the
# host's file mode: this repo is developed on Windows, where the executable
# bit doesn't survive, and CRLF line endings would make the kernel fail to
# find /bin/sh with a confusing "no such file or directory".
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Not root: a bug in the app (or a dependency) that yields code execution
# then lands as an unprivileged user that can't rewrite the app's own code.
# /app stays root-owned and read-only to it; the runtime/ and secrets/ bind
# mounts are the only places it needs.
RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin app
USER app

EXPOSE 8000

# The entrypoint brings the schema up to date, then execs this.
ENTRYPOINT ["/app/entrypoint.sh"]
# --proxy-headers: behind tailscale funnel every request arrives from the same
# proxy address, so slowapi's per-IP limits collapsed into one shared bucket
# (a stranger could burn the login quota and lock the owner out). Trusting
# X-Forwarded-For from anyone is safe only because docker-compose publishes
# 8000 on 127.0.0.1 — nothing but the local proxy can reach this port.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
