import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.router import router
from app.database import close_db
from app.ai_client import close_client

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    fmt = "[%(asctime)s] %(levelname)-7s %(name)s | %(message)s"
    datefmt = "%H:%M:%S"

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    app_level = logging.DEBUG if settings.debug else logging.INFO
    for name in ("app", "app.ai_client", "app.prompt_builder", "app.router"):
        lg = logging.getLogger(name)
        lg.setLevel(app_level)
        lg.handlers.clear()
        lg.addHandler(handler)
        lg.propagate = False

    for name in ("httpx", "httpcore", "aiosqlite"):
        logging.getLogger(name).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    logger = logging.getLogger("app.main")
    logger.info("Server starting (debug=%s, auth=%s)", settings.debug,
                "enabled" if settings.auth_token else "disabled")
    logger.info("AI model: %s @ %s", settings.ai_model, settings.ai_base_url)
    yield
    logger.info("Server shutting down")
    await close_client()
    await close_db()


app = FastAPI(title="OCS AI Question Bank", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Token auth middleware — only guards /query and /reload, not /health /stats /
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path.rstrip("/")
    if path in ("/query", "/reload") and settings.auth_token:
        # Check token in query params (GET) or try to parse from body
        token = request.query_params.get("token")
        if not token and request.method == "POST":
            try:
                body = await request.body()
                import json
                data = json.loads(body)
                token = data.get("token")
            except Exception:
                pass

        if token != settings.auth_token:
            logger.warning("Auth rejected: token=%s from %s", token, request.client)
            return JSONResponse(
                status_code=200,
                content={"code": 1, "data": None, "msg": "Invalid or missing token"},
            )

    return await call_next(request)


app.include_router(router)
