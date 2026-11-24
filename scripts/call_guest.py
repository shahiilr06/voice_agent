"""
Direct Calling CLI Script.
Trigger an immediate phone call to the guest mobile phone (+91 9994388773)
via Twilio (+1 515 758 7590) bridged to LiveKit SIP and Maya AI Receptionist.

Usage:
    python scripts/call_guest.py
    python scripts/call_guest.py +919994388773
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from api.services.twilio_service import dial_twilio_call, check_twilio_config


async def main():
    target_phone = sys.argv[1] if len(sys.argv) > 1 else "+919994388773"

    print("=" * 60)
    print("📞 Sunrise International Hotel — Direct AI Voice Call")
    print("=" * 60)

    # 1. Check Configuration
    status = check_twilio_config()
    print(f"Twilio Account Status : {status.status.upper()}")
    print(f"From (Twilio Number)  : {status.twilio_phone_number}")
    print(f"To (Target Phone)     : {target_phone}")
    print(f"LiveKit Cloud SIP     : {status.livekit_sip_uri}")
    print("-" * 60)

    if not status.configured:
        print("❌ Error: Twilio credentials not configured in .env")
        if status.instructions:
            print(status.instructions)
        return

    # 2. Dispatch Call
    print(f"🚀 Placing telephone call to {target_phone}...")
    res = await dial_twilio_call(to_phone=target_phone)

    if res.success:
        print("=" * 60)
        print("✅ CALL SUCCESSFULLY DISPATCHED!")
        print(f"   Call SID   : {res.call_sid}")
        print(f"   Status     : {res.status}")
        print(f"   Room Name  : {res.room_name}")
        print("=" * 60)
        print(f"📱 Please answer your phone ({target_phone}) now!")
        print("   Maya will greet you in English and Tamil and assist you with your booking.")
    else:
        print("❌ Call Failed:")
        print(f"   Message : {res.message}")
        if res.instructions:
            print(f"   Help    : {res.instructions}")


if __name__ == "__main__":
    asyncio.run(main())
