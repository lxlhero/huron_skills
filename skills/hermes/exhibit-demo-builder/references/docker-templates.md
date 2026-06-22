# Example: Full-stack single-image Docker demo platform

## Dockerfile.single (multi-stage build)

```dockerfile
# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY index.html tsconfig*.json vite.config.ts ./
COPY src/ ./src/
RUN npm run build

# Stage 2: Python backend + nginx
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx supervisor && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-builder /app/dist/ /usr/share/nginx/html/
COPY nginx-single.conf /etc/nginx/conf.d/default.conf
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY start.sh ./
RUN chmod +x start.sh

# Remove default nginx server block to avoid port conflict
RUN rm -f /etc/nginx/sites-enabled/default

RUN mkdir -p /app/data
EXPOSE 80
CMD ["./start.sh"]
```

## supervisord.conf

```ini
[supervisord]
nodaemon=true
user=root

[program:uvicorn]
command=uvicorn main:app --host 127.0.0.1 --port 8000
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:nginx]
command=nginx -g "daemon off;"
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

## nginx-single.conf

```nginx
server {
    listen 80;
    server_name localhost;

    root /usr/share/nginx/html;
    index index.html;

    # Static files
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy to FastAPI backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

## start.sh

```bash
#!/bin/sh
set -e
# Start supervisord which manages both uvicorn and nginx
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
```

## Dev docker-compose.yml

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - data:/app/data
    environment:
      - DATABASE_URL=sqlite:///./data/demo.db

  frontend:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "3000:80"
    depends_on:
      - backend

volumes:
  data:
```
