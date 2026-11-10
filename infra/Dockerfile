FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MARKET_SAGE_WEB_DIR=/app/web
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend
COPY --from=web /web/dist /app/web
WORKDIR /app/backend
