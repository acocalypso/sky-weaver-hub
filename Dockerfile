# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.ts tsconfig*.json tailwind.config.ts ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    SKYWEAVER_ENV=production \
    SKYWEAVER_DEPLOYMENT=docker \
    SKYWEAVER_DATA_DIR=/var/lib/skyweaver \
    SKYWEAVER_CONFIG_DIR=/etc/skyweaver \
    SKYWEAVER_LOG_DIR=/var/log/skyweaver \
    SKYWEAVER_WEB_DIR=/app/web
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates ffmpeg fonts-dejavu-core openssh-client rsync tzdata util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 skyweaver \
    && useradd --uid 10001 --gid skyweaver --create-home skyweaver \
    && mkdir -p /var/lib/skyweaver /etc/skyweaver /var/log/skyweaver \
    && chown skyweaver:skyweaver /var/lib/skyweaver /etc/skyweaver /var/log/skyweaver
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/skyweaver ./backend/skyweaver
COPY --from=frontend /build/dist ./web
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/skyweaver-entrypoint
COPY docker/healthcheck.py ./docker/healthcheck.py
USER skyweaver
EXPOSE 8765
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "/app/docker/healthcheck.py", "api"]
ENTRYPOINT ["skyweaver-entrypoint"]
CMD ["api"]
