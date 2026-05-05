import os
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import init_db, close_db
from app.routers import (
    auth_router, sos_router, medical_router,
    payment_router, analytics_router,
    dispatch_router, ambulance_router,
    verification_router,
)

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("safepulse")

# ── Rate limiter ──────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])

# ── Lifespan ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SafePulse starting up…")
    await init_db()
    os.makedirs("static/reports", exist_ok=True)
    logger.info("SafePulse ready ✓")
    yield
    logger.info("SafePulse shutting down…")
    await close_db()

# ── App ───────────────────────────────────────────────────
app = FastAPI(
    title="SafePulse API",
    version="1.0.0",
    description="Emergency Response System — Backend API",
    lifespan=lifespan,
    # Hide docs in production
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url=None,
)

# ── Middleware ────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Compress responses > 1KB
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restrict to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request timing middleware ─────────────────────────────
@app.middleware("http")
async def add_process_time(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Please try again."}
        )
    duration = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{duration:.1f}"
    if duration > 2000:
        logger.warning(f"Slow request: {request.method} {request.url.path} took {duration:.0f}ms")
    return response

# ── Global exception handlers ─────────────────────────────
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail or "An error occurred"},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        field = " → ".join(str(x) for x in err["loc"] if x != "body")
        errors.append(f"{field}: {err['msg']}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": errors},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong. Our team has been notified."},
    )

# ── Static files ──────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Routers ───────────────────────────────────────────────
app.include_router(auth_router.router)
app.include_router(sos_router.router)
app.include_router(medical_router.router)
app.include_router(payment_router.router)
app.include_router(analytics_router.router)
app.include_router(dispatch_router.router)
app.include_router(ambulance_router.router)
app.include_router(verification_router.router)

# ── Core routes ───────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard", include_in_schema=False)
async def dashboard():
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.normpath(os.path.join(base, "..", "..", "web", "index.html"))
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"detail": "Dashboard not found"})
    return FileResponse(path, media_type="text/html")

@app.get("/health", tags=["System"])
async def health(request: Request):
    from app.database import engine
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "SafePulse API",
        "version": "1.0.0",
        "database": "connected" if db_ok else "unreachable",
        "environment": settings.ENVIRONMENT,
    }
