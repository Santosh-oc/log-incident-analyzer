# --- Stage 1: build the frontend -------------------------------------------
FROM node:24-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# The base path is baked in at build time; the platform injects
# DKUBEX_BASE_PATH at runtime, so build with the chart's known prefix.
ARG DKUBEX_BASE_PATH=/log-incident-analyzer
ENV DKUBEX_BASE_PATH=$DKUBEX_BASE_PATH
RUN npm run build

# --- Stage 2: python runtime -------------------------------------------------
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /build/dist ./frontend/dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
