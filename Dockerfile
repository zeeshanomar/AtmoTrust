FROM node:22-alpine AS frontend_build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY data/prepared/demo_v1/ ./data/prepared/demo_v1/
COPY artifacts/demo_v1/ ./artifacts/demo_v1/
COPY scripts/seed_accounts.py scripts/start_hosted.sh ./scripts/
COPY frontend/src/demo_accounts.json ./frontend/src/demo_accounts.json
COPY --from=frontend_build /app/frontend/dist ./frontend/dist
EXPOSE 10000
CMD ["sh", "scripts/start_hosted.sh"]
