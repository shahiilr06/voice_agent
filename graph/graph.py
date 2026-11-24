"""
LangGraph graph builder for the hotel voice booking assistant.
"""
import os
import functools
import requests
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from graph.state import BookingState
from graph.nodes import (
    detect_language_node,
    extract_slots_node,
    check_availability_node,
    create_booking_node,
    receptionist_agent_node,
)
from graph.edges import route_after_extract


class SarvamChatModel:
    """
    Direct client for Sarvam AI chat completions API (sarvam-105b-conversations).
    """
    def __init__(self, api_key: str, model: str = "sarvam-105b-conversations"):
        self.api_key = api_key
        self.model = model
        self.url = "https://api.sarvam.ai/v1/chat/completions"

    def invoke(self, messages):
        formatted = []
        for m in messages:
            role = "user"
            if isinstance(m, SystemMessage) or getattr(m, "type", None) == "system":
                role = "system"
            elif isinstance(m, AIMessage) or getattr(m, "type", None) == "ai":
                role = "assistant"
            formatted.append({"role": role, "content": getattr(m, "content", str(m))})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(
                self.url,
                json={"model": self.model, "messages": formatted, "temperature": 0.3},
                headers=headers,
                timeout=5,
            )
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"]
                return AIMessage(content=text)
        except Exception:
            pass
        return None


def get_llm():
    """Initialize LLM via Sarvam, OpenRouter, or fallback."""
    sarvam_key = os.getenv("SARVAM_API_KEY")
    llm_model = os.getenv("LLM_MODEL", "sarvam-105b-conversations")

    if sarvam_key:
        return SarvamChatModel(api_key=sarvam_key, model=llm_model)

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        try:
            from langchain_community.chat_models import ChatOpenAI
            return ChatOpenAI(
                model=os.getenv("OPENROUTER_MODEL", "google/gemma-2-9b-it:free"),
                openai_api_key=openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.3,
            )
        except Exception:
            pass

    return None


def build_hotel_graph(checkpointer=None):
    """
    Compile StateGraph for real-time voice hotel assistant.
    Flow:
    START -> detect_language -> extract_slots ->
    conditional [check_availability | create_booking | receptionist_agent]
    """
    llm = get_llm()

    workflow = StateGraph(BookingState)

    # 1. Register Nodes
    workflow.add_node("detect_language", detect_language_node)
    workflow.add_node("extract_slots", functools.partial(extract_slots_node, llm=llm))
    workflow.add_node("check_availability", check_availability_node)
    workflow.add_node("create_booking", create_booking_node)
    workflow.add_node("receptionist_agent", functools.partial(receptionist_agent_node, llm=llm))

    # 2. Register Edges
    workflow.add_edge(START, "detect_language")
    workflow.add_edge("detect_language", "extract_slots")

    workflow.add_conditional_edges(
        "extract_slots",
        route_after_extract,
        {
            "check_availability": "check_availability",
            "create_booking": "create_booking",
            "receptionist_agent": "receptionist_agent",
        }
    )

    workflow.add_edge("check_availability", "receptionist_agent")
    workflow.add_edge("create_booking", "receptionist_agent")
    workflow.add_edge("receptionist_agent", END)

    return workflow.compile(checkpointer=checkpointer)
