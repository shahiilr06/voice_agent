from datetime import date, timedelta
from langchain_core.messages import HumanMessage
from graph.graph import build_hotel_graph
from graph.nodes import detect_language_node, extract_slots_node


def test_language_detection_english():
    state = {"messages": [HumanMessage(content="Hello, I want to book a deluxe room for two nights.")]}
    res = detect_language_node(state)
    assert res["language"] == "en-IN"


def test_language_detection_defaults():
    state = {"messages": []}
    res = detect_language_node(state)
    assert res["language"] == "en-IN"


def test_slot_extraction_heuristics():
    state = {
        "messages": [
            HumanMessage(content="My name is Ramesh, phone is 9876543210. I need a deluxe room for tomorrow for 2 people.")
        ],
        "room_type": None,
        "guest_phone": None,
        "num_guests": None,
        "check_in": None,
    }
    extracted = extract_slots_node(state)
    assert extracted.get("guest_phone") == "9876543210"
    assert extracted.get("room_type") == "deluxe"
    assert extracted.get("num_guests") == 2
    assert extracted.get("check_in") == (date.today() + timedelta(days=1)).isoformat()


def test_full_graph_dialogue_execution():
    graph = build_hotel_graph()
    initial_state = {
        "messages": [HumanMessage(content="Hi, do you have a deluxe room available tomorrow?")],
        "language": None,
        "guest_name": None,
        "guest_phone": None,
        "guest_email": None,
        "room_type": None,
        "check_in": None,
        "check_out": None,
        "num_guests": None,
        "is_available": False,
        "available_room_id": None,
        "available_room_name": None,
        "price_per_night": None,
        "total_price": None,
        "guest_confirmed": False,
        "booking_confirmed": False,
        "confirmation_code": None,
        "stage": "greeting",
    }
    final_state = graph.invoke(initial_state)
    assert final_state["language"] == "en-IN"
    assert final_state["room_type"] == "deluxe"
    assert len(final_state["messages"]) >= 2
    assert len(final_state["messages"][-1].content) > 0
