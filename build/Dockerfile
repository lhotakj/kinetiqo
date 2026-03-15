# =============================================================================
# Kinetiqo Application Image
# =============================================================================
# Uses the pre-built lhotakj/firebird-python base image which already contains
# the compiled Firebird 5.x client library.  This keeps the application build
# fast (no ~40-minute Firebird compilation).
#
# To rebuild the base image run the "Build Firebird Python Base Image"
# GitHub Actions workflow manually, or use build/build-base.sh locally.
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder — install Python dependencies into an isolated prefix
# -----------------------------------------------------------------------------
FROM python:3.13-alpine AS builder

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install all pip packages to /install so they can be copied cleanly
# into the runtime stage without dragging in the build tools.
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: Runtime — application on top of the Firebird-ready base image
# -----------------------------------------------------------------------------
FROM lhotakj/firebird-python:3.13

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

# dcron is the only extra system package the application itself needs;
# libtommath, libgcc and libpq are already present in the base image.
RUN apk add --no-cache dcron

# Set working directory
WORKDIR /app

# Copy installed Python packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source and the container entrypoint
COPY src ./
COPY build/entrypoint.sh ./

EXPOSE 4444

ENTRYPOINT ["sh", "entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:4444", "--workers", "4", "--timeout", "180", "kinetiqo.web.app:app"]
