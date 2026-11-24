"""
FastAPI application entrypoint.
Configures CORS, life cycle events, routers, and frontend static files.
"""
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from api.database import init_db
from api.routers.rooms import router as rooms_router
from api.routers.bookings import router as bookings_router
from api.routers.livekit import router as livekit_router
from api.routers.sip import router as sip_router
from api.routers.exotel import router as exotel_router
from api.routers.twilio import router as twilio_router
from api.routers.voice import router as voice_router
from api.services.exotel_service import dial_exotel_call
from seeds.seed_data import seed_database

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables and seed sample data non-blockingly
    await asyncio.to_thread(init_db)
    await asyncio.to_thread(seed_database)
    print("🏨 [Sunrise Hotel] Maya AI Local Backend running. Ready for local testing.")
    yield


app = FastAPI(
    title="Sunrise Hotel Voice Assistant API",
    description="Production-grade English hotel voice booking backend with LiveKit SIP telephony.",
    version="2.0.0",
    lifespan=lifespan,
)

# Enable CORS for web frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(livekit_router)
app.include_router(rooms_router)
app.include_router(bookings_router)
app.include_router(sip_router)
app.include_router(exotel_router)
app.include_router(twilio_router)
app.include_router(voice_router)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "AI Hotel Assistant Backend",
        "version": "2.0.0",
        "bilingual_support": ["en-IN", "ta-IN", "tanglish"],
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
def chrome_devtools_probe():
    return Response(status_code=204)


# Mount frontend static directory if exists
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
