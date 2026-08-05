FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Runtime entrypoint: source .env so the provisioned DATABASE_URL is a real env var before the app boots
RUN echo '#!/bin/sh' > /app/entrypoint.sh && echo 'set -e' >> /app/entrypoint.sh && echo 'for f in /app/.env /app/backend/.env ./.env; do [ -f "$f" ] || continue; while IFS= read -r line || [ -n "$line" ]; do case "$line" in \#*) continue;; *=*) key=${line%%=*}; val=${line#*=}; case "$val" in \"*\") val=${val#\"}; val=${val%\"};; esac; export "$key=$val";; esac; done < "$f"; done' >> /app/entrypoint.sh && echo 'if [ ! -f main.py ]; then' >> /app/entrypoint.sh && echo '  for m in app.main src.main backend.main api.main app.api.main; do' >> /app/entrypoint.sh && echo '    p=$(echo "$m" | tr . /);' >> /app/entrypoint.sh && echo '    if [ -f "$p.py" ]; then' >> /app/entrypoint.sh && echo '      echo "from $m import app" > main.py;' >> /app/entrypoint.sh && echo '      echo "entrypoint: no main.py; re-exporting app from $m";' >> /app/entrypoint.sh && echo '      break;' >> /app/entrypoint.sh && echo '    fi;' >> /app/entrypoint.sh && echo '  done;' >> /app/entrypoint.sh && echo 'fi' >> /app/entrypoint.sh && echo 'if [ -f alembic.ini ]; then alembic upgrade head || true; fi' >> /app/entrypoint.sh && echo 'python -c "from app.db import init_db; init_db()" 2>/dev/null || true' >> /app/entrypoint.sh && echo 'if [ -f seed_demo.py ]; then python seed_demo.py || true; fi' >> /app/entrypoint.sh && echo 'exec "$@"' >> /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Base-path routing: this service is served at /health_check_api_71b313_backend
ENV ROOT_PATH=/health_check_api_71b313_backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8000), 3).close()" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--root-path", "/health_check_api_71b313_backend"]
