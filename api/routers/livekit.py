import os
import time
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/livekit", tags=["livekit"])


@router.get("/token")
def generate_livekit_token(
    room: str = Query(default="hotel-voice-lobby"),
    participant: str = Query(default="guest"),
):
    """
    Issue a signed WebRTC LiveKit JWT for client connection.
    Uses livekit-api if available, falling back to RFC 7519 PyJWT.
    """
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    ws_url = os.getenv("LIVEKIT_URL")

    if not api_key or not api_secret or not ws_url:
        raise HTTPException(
            status_code=500,
            detail="LiveKit credentials (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) not properly configured in environment.",
        )

    # Append random timestamp suffix to participant identity to prevent session collisions
    unique_identity = f"{participant}-{int(time.time())}"

    # Try livekit.api if installed
    try:
        from livekit import api as lk_api
        token = (
            lk_api.AccessToken(api_key, api_secret)
            .with_identity(unique_identity)
            .with_name("Hotel Guest")
            .with_grants(
                lk_api.VideoGrants(
                    room_join=True,
                    room=room,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .to_jwt()
        )
    except ImportError:
        # Fallback to standard PyJWT signature compatible with all LiveKit SFUs
        import jwt
        now = int(time.time())
        claims = {
            "sub": unique_identity,
            "iss": api_key,
            "nbf": now - 5,
            "exp": now + (6 * 3600),
            "name": "Hotel Guest",
            "video": {
                "roomJoin": True,
                "room": room,
                "canPublish": True,
                "canSubscribe": True,
                "canPublishData": True,
            },
        }
        token = jwt.encode(claims, api_secret, algorithm="HS256")

    return {
        "success": True,
        "token": token,
        "url": ws_url,
        "room": room,
        "identity": unique_identity,
    }

