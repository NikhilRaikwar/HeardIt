import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.core.config import get_settings
from app.core.errors import AppError
from app.db import close, require_database
from app.heardit import initialize_heardit, router as heardit_router

logger = logging.getLogger("heardit.api")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        await initialize_heardit(await require_database())
        logger.info("mongodb_ready")
    except AppError:
        logger.warning("mongodb_unavailable_at_startup")
    yield
    await close()


app = FastAPI(
    title="HeardIt API",
    version="1.0.0",
    description="Create Fish Audio listening experiments and measure what people hear.",
    lifespan=lifespan,
)
app.include_router(heardit_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Management-Token"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = time.monotonic()
    if request.method == "POST":
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > 500_000):
            return JSONResponse(
                {"error": {"code": "payload_too_large", "message": "Request exceeds the 500 KB limit."}},
                status_code=413,
            )
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%d",
        request.method,
        request.url.path,
        response.status_code,
        (time.monotonic() - started) * 1000,
    )
    return response


@app.exception_handler(AppError)
async def app_error(request: Request, error: AppError):
    return JSONResponse(
        {"error": {"code": error.code, "message": error.message, "details": error.details}},
        status_code=error.status,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    details = [{"loc": list(item["loc"]), "message": item["msg"], "type": item["type"]} for item in error.errors()]
    return JSONResponse(
        {"error": {"code": "validation_error", "message": "Check the request fields.", "details": details}},
        status_code=422,
    )


@app.exception_handler(PyMongoError)
async def mongo_error(request: Request, error: PyMongoError):
    logger.error("database_operation_failed type=%s", type(error).__name__)
    return JSONResponse(
        {"error": {"code": "database_unavailable", "message": "The database is unavailable. Retry when MongoDB is ready."}},
        status_code=503,
    )
