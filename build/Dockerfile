# Stage 1: Builder - Install dependencies
FROM python:3.13-alpine AS builder

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies to a specific directory
# --no-cache-dir: Don't cache downloaded packages (saves space)
# --prefix=/install: Install to /install directory for easy copying
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime - Minimal final image
FROM python:3.13-alpine

ARG VERSION
LABEL maintainer="jarda@lhotak.net" \
      version=$VERSION \
      description="Kinetiqo sync tool"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FULL_SYNC="" \
    FAST_SYNC="" \
    PYTHONPATH=/usr/local/lib/python3.13/site-packages

# Set working directory
WORKDIR /app

# Install runtime dependencies (dcron)
# We need libpq for psycopg2 (PostgreSQL driver) if using the binary version,
# but psycopg2-binary usually bundles it. However, on Alpine, sometimes it's safer to have libpq.
# Since we are using psycopg2-binary, it might work without, but let's keep it minimal.
RUN apk add --no-cache dcron libpq

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY src ./
COPY build/entrypoint.sh ./

EXPOSE 8000

ENTRYPOINT ["sh", "entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "kinetiqo.web.app:app"]
