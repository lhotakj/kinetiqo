# =============================================================================
# Kinetiqo Application Image
# =============================================================================
# Uses the pre-built lhotakj/firebird-python base image which contains:
#   • Compiled Firebird 5.x client library
#   • System Chromium browser with all its deps
#   • Playwright ENV vars (PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH, etc.)
#
# Because the base already has Chromium, this image does NOT run
# `playwright install chromium` — saving ~465 MB from every app build.
# Playwright uses the system Chromium via PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH.
#
# To rebuild the base image: build/build-base.sh  (or GitHub Actions)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder — install Python dependencies into an isolated prefix
# -----------------------------------------------------------------------------
FROM python:3.14-slim AS builder

WORKDIR /app
COPY requirements.txt .

# No build tools needed — every package in requirements.txt ships a
# pre-built manylinux binary wheel so nothing is compiled from source.
# PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 suppresses any browser download hooks.
# --no-compile skips .pyc pre-compilation (~40 MB saved).
# Post-install find cleanup strips test dirs and bytecode (~80-100 MB saved).
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
RUN pip install --no-cache-dir --no-compile --prefix=/install -r requirements.txt \
    && find /install -type d -name "tests"       -exec rm -rf {} + 2>/dev/null || true \
    && find /install -type d -name "test"        -exec rm -rf {} + 2>/dev/null || true \
    && find /install -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find /install -name "*.pyc" -delete \
    && find /install -name "*.pyo" -delete

# -----------------------------------------------------------------------------
# Stage 2: Runtime — application on top of the Firebird + Chromium base image
# -----------------------------------------------------------------------------
FROM lhotakj/firebird-python:3.14

ARG VERSION
LABEL maintainer="jarda@lhotak.net" \
      version=$VERSION \
      description="Kinetiqo sync tool"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FULL_SYNC="" \
    FAST_SYNC="" \
    PYTHONPATH=/usr/local/lib/python3.14/site-packages
# LD_LIBRARY_PATH, FIREBIRD_LIB, PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
# PLAYWRIGHT_BROWSERS_PATH, PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD are all
# inherited from the base image ENV — no need to repeat them here.

WORKDIR /app

# Copy installed Python packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source and the container entrypoint
COPY src ./
COPY build/entrypoint.sh ./

# Verify Chromium is reachable (sanity check — fails build if broken).
# Then strip any bytecode / test directories that binary wheels may have
# re-introduced into /usr/local/lib via the COPY above.
# Everything else (apt lists, man pages, locales, doc, pip, setuptools)
# was already cleaned in the base image — no need to repeat it here.
RUN chromium --version \
    && find /usr/local/lib -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib -name "*.pyc" -delete 2>/dev/null || true \
    && find /usr/local/lib -name "*.pyo" -delete 2>/dev/null || true \
    && find /usr/local/lib -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib -type d -name "test"  -exec rm -rf {} + 2>/dev/null || true

EXPOSE 4444

ENTRYPOINT ["sh", "entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:4444", "--workers", "4", "--timeout", "180", "kinetiqo.web.app:app"]
