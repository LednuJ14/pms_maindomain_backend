# Multi-stage build for Python/Flask PMS backend
# Uses python:3.12-alpine for minimal image size (~50MB vs ~150MB slim)

# ── Stage 1: Build dependencies ──────────────────────────────────────
FROM python:3.12-alpine AS builder
WORKDIR /app

# Install build-time deps for Pillow, cryptography, PyMySQL, etc.
RUN apk add --no-cache \
    gcc musl-dev libffi-dev openssl-dev \
    jpeg-dev libpng-dev zlib-dev freetype-dev

COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Production runner ───────────────────────────────────────
FROM python:3.12-alpine AS runner
WORKDIR /app

# Runtime libs only (no compilers)
RUN apk add --no-cache \
    libjpeg libpng zlib freetype libffi openssl

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create uploads directory (writable at runtime)
RUN mkdir -p /app/uploads && chmod 755 /app/uploads

ENV FLASK_ENV=production
EXPOSE 5000

# Run with Gunicorn (4 workers, bind to all interfaces)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "app:create_app()"]
