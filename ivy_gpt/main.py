from contextlib import asynccontextmanager

import sentry_sdk
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ivy_gpt.config import apply_runtime_environment, ensure_runtime_dirs, settings
from ivy_gpt.logging_config import configure_logging
from ivy_gpt.middleware.request_logging import RequestLoggingMiddleware


configure_logging()
apply_runtime_environment()
ensure_runtime_dirs()

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        send_default_pii=settings.sentry_send_default_pii,
        enable_logs=settings.sentry_enable_logs,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )

from ivy_gpt.core.agent import close_agent_connections
from ivy_gpt.db.session import init_db
from ivy_gpt.routes.auth import router as auth_router
from ivy_gpt.routes.chat import router as chat_router
from ivy_gpt.routes.conversations import router as conversations_router
from ivy_gpt.routes.home import router as home_router
from ivy_gpt.routes.mcp import router as mcp_router
from ivy_gpt.routes.uploads import router as uploads_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        yield
    finally:
        await close_agent_connections()


cors_origins = settings.cors_origins

app = FastAPI(lifespan=lifespan)

app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(auth_router)
app.include_router(home_router)
app.include_router(conversations_router)
app.include_router(uploads_router)
app.include_router(chat_router)
app.include_router(mcp_router)


if __name__ == "__main__":
    uvicorn.run(
        "ivy_gpt.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True
    )
