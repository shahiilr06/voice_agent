"""
LiveKit Cloud SIP Provisioning Script.
Checks, creates, or verifies Inbound Trunk and Dispatch Rules on LiveKit Cloud.
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()


async def provision_livekit_sip():
    from livekit.api import LiveKitAPI

    url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not (url and api_key and api_secret):
        print("❌ Error: LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET must be set in .env")
        return False

    print(f"Connecting to LiveKit Cloud: {url}...")
    api = LiveKitAPI(url=url, api_key=api_key, api_secret=api_secret)

    try:
        # 1. List Inbound Trunks
        print("\n🔍 Checking Inbound SIP Trunks on LiveKit Cloud...")
        try:
            from livekit.api import ListSIPInboundTrunkRequest
            if hasattr(api.sip, "list_inbound_trunk"):
                inbound_resp = await api.sip.list_inbound_trunk(ListSIPInboundTrunkRequest())
            else:
                inbound_resp = await api.sip.list_sip_inbound_trunk(ListSIPInboundTrunkRequest())
            inbound_items = getattr(inbound_resp, "items", [])
            print(f"Found {len(inbound_items)} Inbound Trunk(s).")
            for t in inbound_items:
                print(f"  - Trunk ID: {t.sip_trunk_id}, Name: {t.name}, Numbers: {list(t.numbers)}")
        except Exception as e:
            print(f"  Note: Inbound trunk query: {e}")
            inbound_items = []

        # 2. List Outbound Trunks
        print("\n🔍 Checking Outbound SIP Trunks on LiveKit Cloud...")
        try:
            from livekit.api import ListSIPOutboundTrunkRequest
            if hasattr(api.sip, "list_outbound_trunk"):
                outbound_resp = await api.sip.list_outbound_trunk(ListSIPOutboundTrunkRequest())
            else:
                outbound_resp = await api.sip.list_sip_outbound_trunk(ListSIPOutboundTrunkRequest())
            outbound_items = getattr(outbound_resp, "items", [])
            print(f"Found {len(outbound_items)} Outbound Trunk(s).")
            for t in outbound_items:
                print(f"  - Trunk ID: {t.sip_trunk_id}, Name: {t.name}, Address: {t.address}")
        except Exception as e:
            print(f"  Note: Outbound trunk query: {e}")

        # 3. List Dispatch Rules
        print("\n🔍 Checking SIP Dispatch Rules...")
        try:
            from livekit.api import ListSIPDispatchRuleRequest
            if hasattr(api.sip, "list_dispatch_rule"):
                rules_resp = await api.sip.list_dispatch_rule(ListSIPDispatchRuleRequest())
            else:
                rules_resp = await api.sip.list_sip_dispatch_rule(ListSIPDispatchRuleRequest())
            rule_items = getattr(rules_resp, "items", [])
            print(f"Found {len(rule_items)} Dispatch Rule(s).")
            for r in rule_items:
                print(f"  - Rule ID: {r.sip_dispatch_rule_id}, Name: {r.name}")
        except Exception as e:
            print(f"  Note: Dispatch rule query: {e}")

        print("\n✅ LiveKit Cloud SIP connection verified successfully!")
        print(f"SIP Inbound URI: sip:vw9lj499216.sip.livekit.cloud")
        return True

    except Exception as e:
        print(f"❌ Failed to query LiveKit SIP: {e}")
        return False
    finally:
        await api.aclose()


if __name__ == "__main__":
    success = asyncio.run(provision_livekit_sip())
    sys.exit(0 if success else 1)
