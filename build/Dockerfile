# =============================================================================
# Kinetiqo Application Image
# =============================================================================
# Uses the pre-built lhotakj/firebird-python base image (Debian slim / glibc)
# which already contains the compiled Firebird 5.x client library.
#
# Because the base is glibc-based, Playwright's own bundled Chromium binary
# runs natively — no system Chromium package required.
#
# To rebuild the base image run the "Build Firebird Python Base Image"
# GitHub Actions workflow manually, or use build/build-base.sh locally.
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder — install Python dependencies into an isolated prefix
# -----------------------------------------------------------------------------
FROM python:3.13-slim AS builder

WORKDIR /app
COPY requirements.txt .

# Minimal build deps — most packages ship manylinux binary wheels on Debian,
# so compilation is rarely needed.  gcc + libffi-dev cover the edge cases.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install all Python packages.
# psycopg2-binary works as-is on Debian/glibc — no source build needed.
# --no-compile: skip .pyc pre-compilation (saves ~40 MB in the layer).
# Post-install cleanup removes test directories (pandas/tests, numpy/tests,
# etc.) and any stray bytecode — together this saves another ~80-100 MB.
RUN pip install --no-cache-dir --no-compile --prefix=/install -r requirements.txt \
    && find /install -type d -name "tests"      -exec rm -rf {} + 2>/dev/null || true \
    && find /install -type d -name "test"       -exec rm -rf {} + 2>/dev/null || true \
    && find /install -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find /install -name "*.pyc" -delete \
    && find /install -name "*.pyo" -delete

# -----------------------------------------------------------------------------
# Stage 2: Runtime — application on top of the Firebird-ready base image
# -----------------------------------------------------------------------------
FROM lhotakj/firebird-debian-python:3.13

ARG VERSION
LABEL maintainer="jarda@lhotak.net" \
      version=$VERSION \
      description="Kinetiqo sync tool"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FULL_SYNC="" \
    FAST_SYNC="" \
    PYTHONPATH=/usr/local/lib/python3.13/site-packages \
    LD_LIBRARY_PATH=/usr/local/lib \
    FIREBIRD_LIB=/usr/local/lib/libfbclient.so

# Set working directory
WORKDIR /app

# Copy installed Python packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source and the container entrypoint
COPY src ./
COPY build/entrypoint.sh ./

# Download Playwright's version-matched Chromium binary and install its
# system dependencies (libnss3, libatk, libgbm, etc.) via apt.
# This layer is cached by Docker and only re-runs when the playwright
# package version changes.
RUN playwright install chromium --with-deps \
    && rm -rf /var/lib/apt/lists/* \
    && find /usr/share/doc -mindepth 1 -maxdepth 1 -not -name "libc6" -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf /usr/share/man /usr/share/groff /usr/share/info /usr/share/lintian

EXPOSE 4444

ENTRYPOINT ["sh", "entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:4444", "--workers", "4", "--timeout", "180", "kinetiqo.web.app:app"]
