import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()  # MUST be before any router imports so env vars are available at module load

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import detect, classify, detections
from routers import stream, models as models_router, logs as logs_router
from routers import drone as drone_router
from routers import media as media_router
from routers import responders as responders_router
from routers import missions as missions_router
from routers import live as live_router
from routers import alerts as alerts_router
from routers import auth as auth_router
from routers import review as review_router
from routers.deps import SIGNED_IN
from services import feed_registry
from services import telemetry_sources
from services.yolo_model import load_all, model_info, model_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rescueeye.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load both AI models (victim detection + damage classification)
    logger.info("[startup] Loading AI models ...")
    load_all()
    status = model_status()
    logger.info(f"[startup] Victim model: {status['victim_model']['version']}  "
                f"({status['victim_model']['weights']})")
    logger.info(f"[startup] Damage model: {status['damage_model']['version']}  "
                f"({status['damage_model']['weights']})")

    # Telemetry: a real aircraft is used whenever one reports; the simulated
    # flight model is only the fallback.
    mode = telemetry_sources.configure()
    logger.info(f"[startup] Telemetry source: {mode}")

    # Start MJPEG stream producer
    logger.info("[startup] Starting stream producer ...")
    stream.startup()

    yield

    logger.info("[shutdown] Stopping stream producer ...")
    stream.shutdown()


app = FastAPI(
    title="RescueEye Detection API",
    description="Phase 3 — custom YOLOv8 victim detection + damage classification",
    version="0.3.0",
    lifespan=lifespan,
)

# Vite claims 5173 but silently moves to 5174, 5175 ... when the port is taken
# (a second `npm run dev`, a stale server), and it can be reached on either
# localhost or 127.0.0.1. A single-origin default means that perfectly ordinary
# situation blocks every API call, and the browser reports it as a failed
# request — so the UI says "Cannot reach the detection API. Is it running?"
# about an API that is running fine. Allow the local dev range explicitly.
#
# ALLOWED_ORIGINS overrides this entirely, so a real deployment still pins its
# own origins and inherits none of this.
_DEV_ORIGINS = [
    f"http://{host}:{port}"
    for host in ("localhost", "127.0.0.1")
    for port in range(5173, 5181)
] + [
    # The Android app (Capacitor) serves its bundled pages from this origin.
    "https://localhost",
]

_configured = os.getenv("ALLOWED_ORIGINS", "").strip()
allowed_origins = [o.strip() for o in _configured.split(",") if o.strip()] if _configured else _DEV_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info(f"[startup] CORS allowed origins: {', '.join(allowed_origins)}")

app.include_router(detect.router,         prefix="/detect",     tags=["detection"], dependencies=[SIGNED_IN])
app.include_router(classify.router,       prefix="/classify",   tags=["classification"], dependencies=[SIGNED_IN])
app.include_router(stream.router,         prefix="/stream",     tags=["stream"], dependencies=[SIGNED_IN])
app.include_router(detections.router,     prefix="/detections", tags=["detections"], dependencies=[SIGNED_IN])
app.include_router(models_router.router,  prefix="/models",     tags=["models"], dependencies=[SIGNED_IN])
app.include_router(logs_router.router,    prefix="/logs",       tags=["logs"], dependencies=[SIGNED_IN])
app.include_router(drone_router.router,   prefix="/drone",      tags=["drone"])  # guarded per endpoint: telemetry also accepts a device key
app.include_router(media_router.router,   prefix="/media",      tags=["media"], dependencies=[SIGNED_IN])
app.include_router(responders_router.router, prefix="/responders", tags=["responders"], dependencies=[SIGNED_IN])
app.include_router(missions_router.router,  prefix="/missions",   tags=["missions"], dependencies=[SIGNED_IN])
app.include_router(live_router.router,      prefix="/live",       tags=["live"])
app.include_router(auth_router.router,      prefix="/auth",       tags=["auth"])
app.include_router(review_router.router,    prefix="/review",     tags=["review"], dependencies=[SIGNED_IN])
app.include_router(alerts_router.router,    prefix="/alerts",     tags=["alerts"], dependencies=[SIGNED_IN])


@app.get("/health", tags=["system"])
async def health():
    # stream_active/stream_source describe the primary feed, preserving the
    # shape this endpoint had when the platform carried a single feed.
    primary = feed_registry.primary_feed()
    return {
        "status":        "ok",
        "service":       "rescueeye-api",
        "version":       "0.3.0",
        "phase":         "3-custom-models",
        "models":        model_info(),
        "stream_active": bool(primary and primary.active),
        "stream_source": primary.producer if primary else "none",
        "feed_count":    feed_registry.count(),
        "max_feeds":     feed_registry.MAX_FEEDS,
    }
