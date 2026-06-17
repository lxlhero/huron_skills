# Backend Template (FastAPI + SQLite + SQLAlchemy)

## backend/main.py

```python
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import engine, Base, SessionLocal, get_db, init_db
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import os

# ========== Pydantic Schemas ==========
# Keep schemas in sync with frontend TypeScript types in src/types/*.ts
# Every field the frontend expects MUST be in the schema

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    init_db()  # Pre-seed database
    yield

app = FastAPI(title="<Project Name> API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ok"}

# ========== Auth (Mock) ==========
class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/login")
def login(req: LoginRequest):
    # Mock auth: any credentials work for demo
    return {"token": "demo-token-xxx", "user": {"username": req.username, "role": "admin"}}

# ========== CRUD Patterns ==========
# GET /api/items — list with search, filter, pagination
# GET /api/items/{id} — single item
# POST /api/items — create
# PUT /api/items/{id} — update
# DELETE /api/items/{id} — delete
```

## backend/database.py

```python
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "data", "demo.db")
DATABASE_URL = f"sqlite:///{SQLITE_PATH}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Seed database with demo data on first run."""
    db = SessionLocal()
    try:
        existing = db.query(SomeModel).count()
        if existing > 0:
            return  # Already seeded
        # Insert seed data here
        db.add_all([...])
        db.commit()
    finally:
        db.close()
```

## backend/requirements.txt

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.35
pydantic==2.9.0
python-multipart==0.0.12
```

## backend/Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```
