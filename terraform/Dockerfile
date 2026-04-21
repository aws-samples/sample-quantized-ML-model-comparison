# BYOC Container for serving Unsloth GGUF model via llama.cpp
# Uses the official pre-built llama.cpp server image with CUDA support

FROM ghcr.io/ggml-org/llama.cpp:server-cuda

ENV DEBIAN_FRONTEND=noninteractive

# ── Install runtime dependencies ────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        nginx \
        curl \
        ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Install huggingface-hub for model download ─────────────────────────────
RUN pip3 install --no-cache-dir --break-system-packages huggingface-hub[hf_transfer]

ENV HF_HUB_ENABLE_HF_TRANSFER=1

# ── Download model weights at build time ────────────────────────────────────
RUN mkdir -p /models

# Download the Q4_K_M GGUF file (~5 GB)
RUN hf download \
        unsloth/Qwen3-VL-8B-Instruct-GGUF \
        Qwen3-VL-8B-Instruct-Q4_K_M.gguf \
        --local-dir /models \
    && ls -lh /models/Qwen3-VL-8B-Instruct-Q4_K_M.gguf

# Download the mmproj vision projector file
RUN hf download \
        unsloth/Qwen3-VL-8B-Instruct-GGUF \
        mmproj-F16.gguf \
        --local-dir /models \
    && ls -lh /models/mmproj-F16.gguf

# ── Create non-root user and prepare writable directories ────────────────────
RUN useradd -r -s /bin/false appuser \
    && chown -R appuser:appuser /models \
    && mkdir -p /tmp/nginx \
    && chown -R appuser:appuser /tmp/nginx \
    && chown -R appuser:appuser /var/log/nginx \
    && chown -R appuser:appuser /etc/nginx

# ── Copy entrypoint script ──────────────────────────────────────────────────
COPY serving_script/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# ── Health check ────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

# ── Expose SageMaker contract port ──────────────────────────────────────────
EXPOSE 8080

# Run as non-root user — nginx is started via entrypoint which handles
# the port binding before dropping to serve requests
USER appuser

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
