#!/bin/bash
# Entrypoint script for the llama.cpp BYOC container
# Starts llama-server on an internal port and uses nginx as a reverse proxy
# to satisfy the SageMaker inference contract (port 8080, /ping, /invocations).

set -e

# ── Configuration ───────────────────────────────────────────────────────────
MODEL_PATH="/models/Qwen3-VL-8B-Instruct-Q4_K_M.gguf"
MMPROJ_PATH="/models/mmproj-F16.gguf"
LLAMA_HOST="0.0.0.0"
LLAMA_PORT="8081"
NGINX_PORT="8080"

# ── Start llama-server in the background ────────────────────────────────────
echo "Starting llama-server on port ${LLAMA_PORT}..."
/app/llama-server \
    --model "${MODEL_PATH}" \
    --mmproj "${MMPROJ_PATH}" \
    --host "${LLAMA_HOST}" \
    --port "${LLAMA_PORT}" \
    --ctx-size 4096 &

LLAMA_PID=$!

# ── Wait for llama-server to be ready ───────────────────────────────────────
echo "Waiting for llama-server to become ready..."
MAX_RETRIES=120
RETRY_COUNT=0
until curl -sf "http://127.0.0.1:${LLAMA_PORT}/health" > /dev/null 2>&1; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ "${RETRY_COUNT}" -ge "${MAX_RETRIES}" ]; then
        echo "ERROR: llama-server did not become ready after ${MAX_RETRIES} seconds"
        exit 1
    fi
    # Check that the process is still alive
    if ! kill -0 "${LLAMA_PID}" 2>/dev/null; then
        echo "ERROR: llama-server process exited unexpectedly"
        exit 1
    fi
    sleep 1
done
echo "llama-server is ready."

# ── Configure nginx as a reverse proxy ──────────────────────────────────────
cat > /etc/nginx/nginx.conf <<EOF
worker_processes auto;
pid /tmp/nginx/nginx.pid;
error_log /tmp/nginx/error.log warn;

events {
    worker_connections 128;
}

http {
    access_log /tmp/nginx/access.log;
    client_body_temp_path /tmp/nginx/client_body;
    proxy_temp_path /tmp/nginx/proxy;
    fastcgi_temp_path /tmp/nginx/fastcgi;
    uwsgi_temp_path /tmp/nginx/uwsgi;
    scgi_temp_path /tmp/nginx/scgi;

    upstream llama_backend {
        server 127.0.0.1:${LLAMA_PORT};
    }

    server {
        listen ${NGINX_PORT};

        # SageMaker health check endpoint
        location /ping {
            proxy_pass http://llama_backend/health;
            proxy_set_header Host \$host;
        }

        # SageMaker inference endpoint -> llama.cpp chat completions
        location /invocations {
            proxy_pass http://llama_backend/v1/chat/completions;
            proxy_set_header Host \$host;
            proxy_set_header Content-Type "application/json";
            proxy_read_timeout 120s;
            proxy_send_timeout 120s;
        }
    }
}
EOF

# ── Start nginx in the foreground ───────────────────────────────────────────
echo "Starting nginx on port ${NGINX_PORT}..."
exec nginx -g "daemon off;"
