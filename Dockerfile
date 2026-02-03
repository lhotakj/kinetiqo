ARG VERSION="debug"
FROM python:3.14-alpine AS builder

ARG VERSION
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-alpine

ARG VERSION
LABEL maintainer="jarda@lhotak.net"
LABEL version=$VERSION
LABEL description="Kinetiqo sync tool"

RUN apk add --no-cache dcron \
    && adduser -D appuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY version.txt kinetiqo.py entrypoint.sh ./

ENV FULL_SYNC=""
ENV FAST_SYNC=""

ENTRYPOINT ["sh", "entrypoint.sh"]
