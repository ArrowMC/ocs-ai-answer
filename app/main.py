from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.router import router
from app.database import close_db
from app.ai_client import close_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()
    await close_db()


app = FastAPI(title="OCS AI Question Bank", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
