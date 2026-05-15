# =============================================================================
# Kinetiqo Application Image
# =============================================================================
# Uses the pre-built lhotakj/firebird-debian-python base image which contains:
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
FROM python:3.13-slim AS builder

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
# PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH and PLAYWRIGHT_BROWSERS_PATH are
# inherited from the base image ENV — no need to repeat them here.

WORKDIR /app

# Copy installed Python packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source and the container entrypoint
COPY src ./
COPY build/entrypoint.sh ./

# No `playwright install chromium` needed — system Chromium is already
# present in the base image at $PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH.
# Verify Chromium is reachable, then do a thorough final cleanup:
#   • apt lists & cache          (apt leftovers)
#   • pip cache                  (shouldn't exist with --no-cache-dir, belt+braces)
#   • Python bytecode            (PYTHONDONTWRITEBYTECODE covers runtime, this covers COPY artifacts)
#   • __pycache__ dirs           (same)
#   • Package test/doc dirs      (any that survived the builder-stage strip)
#   • Debian doc/man/info        (re-added by any subsequent apt in base)
#   • Unnecessary locale data
#   • Gunicorn & Flask dev files (not needed at runtime)
RUN chromium --version \
    && apt-get clean \
    && rm -rf \
        /var/lib/apt/lists/* \
        /var/cache/apt/archives/* \
        /root/.cache \
        /tmp/* \
        /var/tmp/* \
    && find /usr/local/lib -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib -name "*.pyc" -delete 2>/dev/null || true \
    && find /usr/local/lib -name "*.pyo" -delete 2>/dev/null || true \
    && find /usr/local/lib -type d -name "tests"  -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib -type d -name "test"   -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/share/doc     -mindepth 1 -maxdepth 1 -not -name "libc6" -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf \
        /usr/share/man \
        /usr/share/groff \
        /usr/share/info \
        /usr/share/lintian \
        /usr/share/locale \
        /usr/lib/python3/dist-packages/pip \
        /usr/lib/python3/dist-packages/setuptools

EXPOSE 4444

ENTRYPOINT ["sh", "entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:4444", "--workers", "4", "--timeout", "180", "kinetiqo.web.app:app"]
