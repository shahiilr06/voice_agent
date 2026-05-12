import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from livekit import api

load_dotenv()

app = FastAPI()
STATIC_DIR = Path(__file__).with_name("static")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


LIVEKIT_URL = _required_env("LIVEKIT_URL")
LIVEKIT_API_KEY = _required_env("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = _required_env("LIVEKIT_API_SECRET")
DEFAULT_ROOM = os.getenv("LIVEKIT_ROOM", "hotel-assistant-room")


class TokenRequest(BaseModel):
    room: str = Field(default=DEFAULT_ROOM)
    identity: str | None = Field(default=None)
    name: str | None = Field(default=None)


@app.get("/")
async def get_home():
    index_path = Path(__file__).with_name("index.html")
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.get("/mic-test")
async def get_mic_test():
    test_path = Path(__file__).with_name("mic_test.html")
    return HTMLResponse(content=test_path.read_text(encoding="utf-8"))


@app.post("/livekit/token")
async def create_livekit_token(payload: TokenRequest):
    room_name = (payload.room or DEFAULT_ROOM).strip()
    if not room_name:
        raise HTTPException(status_code=400, detail="room is required")

    identity = payload.identity or f"guest-{secrets.token_hex(4)}"
    display_name = payload.name or identity

    grants = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    )

    token = (
        api.AccessToken(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(display_name)
        .with_grants(grants)
        .to_jwt()
    )

    return {
        "token": token,
        "ws_url": LIVEKIT_URL,
        "room": room_name,
        "identity": identity,
        "name": display_name,
    }


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "transport": "livekit-only"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
