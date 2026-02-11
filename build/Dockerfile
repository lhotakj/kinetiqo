ARG VERSION="debug"
FROM python:3.14-alpine AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-alpine

ARG VERSION
LABEL maintainer="jarda@lhotak.net" \
      version=$VERSION \
      description="Kinetiqo sync tool"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FULL_SYNC="" \
    FAST_SYNC=""

WORKDIR /app

RUN apk add --no-cache dcron

COPY --from=builder /install /usr/local
COPY src ./
COPY build/entrypoint.sh ./

EXPOSE 8000

ENTRYPOINT ["sh", "entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "kinetiqo.web.app:app"]