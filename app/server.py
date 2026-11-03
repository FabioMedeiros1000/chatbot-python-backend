from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app import settings
from app.routers import router
from database import pool


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    pool.close()


app = FastAPI(
    title="Chatbot",
    description="Api para um chatbot simples",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
)

app.include_router(router)
