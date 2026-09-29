# Single-container production image: builds the React UI and serves UI + API from FastAPI.
# Works on Hugging Face Spaces (Docker SDK, port 7860, non-root user) and any container host.
FROM node:20-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    ENERPILOT_FRONTEND_DIST=/app/frontend/dist \
    ENERPILOT_DATA_DIR=/tmp/enerpilot \
    PORT=7860
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
COPY --from=ui /ui/dist /app/frontend/dist
# hosts such as Hugging Face run the container as a non-root user (uid 1000)
RUN useradd -m -u 1000 enerpilot && mkdir -p /tmp/enerpilot && chown -R enerpilot /tmp/enerpilot
USER enerpilot
EXPOSE 7860
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
