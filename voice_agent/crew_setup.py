import os
from crewai import Agent, Crew, Task, LLM
from dotenv import load_dotenv
try:
    from .hotel_api import check_availability, book_room
except ImportError:
    from hotel_api import check_availability, book_room

load_dotenv()
_cached_agents: tuple[Agent, Agent] | None = None


def _build_sarvam_llm() -> LLM:
    sarvam_api_key = os.getenv("SARVAM_API_KEY")
    if not sarvam_api_key:
        raise ValueError("SARVAM_API_KEY is not set. Please configure it in your environment.")

    return LLM(
        model="openai/sarvam-30b",
        base_url="https://api.sarvam.ai/v1",
        api_key=sarvam_api_key,
        extra_headers={"api-subscription-key": sarvam_api_key},
    )


def _build_agents() -> tuple[Agent, Agent]:
    sarvam_llm = _build_sarvam_llm()

    receptionist = Agent(
        role="Hotel Receptionist",
        goal="Provide a friendly and efficient booking experience for guests at Sunrise Hotel.",
        backstory="""You are the welcoming face of Sunrise Hotel. Your job is to talk to guests, 
    gather their booking details (dates, guests, room type), and once confirmed, 
    communicate the final booking status. You are polite, concise, and professional.
    Always speak directly to the guest.""",
        llm=sarvam_llm,
        verbose=False,
        allow_delegation=True,
    )

    booking_manager = Agent(
        role="Booking Manager",
        goal="Accurately check room availability and process bookings using hotel systems.",
        backstory="""You are an expert in the hotel's backend systems. You handle the technical 
    aspects of checking dates and finalizing reservations. You do not talk to guests 
    directly; you provide information to the Receptionist.""",
        tools=[check_availability, book_room],
        llm=sarvam_llm,
        verbose=False,
        allow_delegation=False,
    )

    return receptionist, booking_manager


def _get_agents() -> tuple[Agent, Agent]:
    global _cached_agents
    if _cached_agents is None:
        _cached_agents = _build_agents()
    return _cached_agents

def create_booking_crew(history_str: str, user_input: str):
    """
    Creates a crew to handle the current turn of the conversation.
    """
    receptionist, booking_manager = _get_agents()
    task = Task(
        description=f"""
        Conversation History:
        {history_str}
        
        New User Message: "{user_input}"
        
        Based on the history and the new message:
        1. If details are missing, ask the user for them politely.
        2. If all details are present, check availability.
        3. If available, offer the price and ask to book.
        4. If the user agrees, get their name/phone and book the room.
        
        Final Output: Only provide the text that the Receptionist should speak to the user. 
        Do not include internal thoughts or agent names in the final output.
        Keep it natural for a voice conversation.
        """,
        expected_output="A natural, spoken-word response from the receptionist to the user.",
        agent=receptionist
    )

    return Crew(
        agents=[receptionist, booking_manager],
        tasks=[task],
        verbose=False
    )
