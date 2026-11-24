"""
Database seeder for hotel rooms and FAQs with precomputed dense embeddings.
"""
from sqlalchemy.orm import Session
from api.database import SessionLocal, init_db
from api.models.room import Room
from api.models.faq import FAQ
from api.services.embedding_service import embed_text

ROOMS_DATA = [
    {
        "room_number": "101",
        "name": "Deluxe Ocean View Room",
        "type": "deluxe",
        "floor": 1,
        "max_guests": 2,
        "price_per_night": 4500.00,
        "amenities": ["Ocean View", "Balcony", "King Bed", "Wi-Fi", "AC", "Breakfast"],
        "description": "Spacious room with king bed, ocean view balcony, high-speed Wi-Fi, air conditioning, and complimentary breakfast.",
        "description_ta": "அழகான கடல் காட்சி கொண்ட பால்கனி, பெரிய கட்டில், அதிவேக வைஃபை, ஏசி மற்றும் இலவச காலை உணவுடன் கூடிய ஆடம்பர அறை.",
    },
    {
        "room_number": "201",
        "name": "Executive Luxury Suite",
        "type": "suite",
        "floor": 2,
        "max_guests": 3,
        "price_per_night": 7500.00,
        "amenities": ["Living Room", "Jacuzzi", "Panoramic View", "Mini Bar", "Butler Service"],
        "description": "Luxury suite featuring a separate living room, jacuzzi, panoramic skyline view, mini bar, and 24/7 concierge service.",
        "description_ta": "தனி வாழ்க்கை அறை, ஜக்குஸி குளியல் தொட்டி, பரந்த நகரக் காட்சி மற்றும் 24 மணி நேர வரவேற்பு சேவையுடன் கூடிய விஐபி சூட் அறை.",
    },
    {
        "room_number": "102",
        "name": "Standard Comfort Room",
        "type": "standard",
        "floor": 1,
        "max_guests": 2,
        "price_per_night": 2800.00,
        "amenities": ["Queen Bed", "Workstation", "Smart TV", "Garden View", "AC"],
        "description": "Cozy modern room with queen-size bed, ergonomic workstation, smart TV, and peaceful garden view.",
        "description_ta": "அமைதியான தோட்டம் காட்சி, குயீன் பெட், ஸ்மார்ட் டிவி மற்றும் ஏசியுடன் கூடிய வசதியான நவீன அறை.",
    },
    {
        "room_number": "301",
        "name": "Royal Family Suite",
        "type": "family",
        "floor": 3,
        "max_guests": 4,
        "price_per_night": 9500.00,
        "amenities": ["Two Bedrooms", "Dining Area", "Sea View", "Kitchenette", "Bathtub"],
        "description": "Two interconnected bedrooms, separate dining area, kitchenette, bathtub, and beautiful sea view, perfect for families.",
        "description_ta": "குடும்பங்களுக்கான இரண்டு படுக்கையறைகள், சாப்பாட்டு அறை, சமையலறை மற்றும் அழகான கடல் காட்சியுடன் கூடிய குடும்ப அறை.",
    },
    {
        "room_number": "103",
        "name": "Budget Single Room",
        "type": "standard",
        "floor": 1,
        "max_guests": 1,
        "price_per_night": 1800.00,
        "amenities": ["Single Bed", "Wi-Fi", "Work Desk", "AC"],
        "description": "Compact single room with private bathroom, fast Wi-Fi, and work desk, ideal for solo and business travelers.",
        "description_ta": "தனியாக பயணம் செய்வோருக்கான சிறிய தனி அறை, அதிவேக வைஃபை, மேஜை மற்றும் ஏசி வசதியுடன்.",
    },
]

FAQS_DATA = [
    {
        "category": "timings",
        "question_en": "What are the check-in and check-out timings?",
        "answer_en": "Check-in time is at 2:00 PM and check-out time is at 11:00 AM. Early check-in is subject to room availability.",
        "question_ta": "செக்-இன் மற்றும் செக்-அவுட் நேரம் என்ன?",
        "answer_ta": "செக்-இன் நேரம் மதியம் 2:00 மணி மற்றும் செக்-அவுட் நேரம் காலை 11:00 மணி. முன்கூட்டியே செக்-இன் கிடைப்பது அறையின் நிலையைப் பொறுத்தது.",
    },
    {
        "category": "cancellation",
        "question_en": "What is your cancellation policy?",
        "answer_en": "You can cancel your booking free of charge up to 24 hours before your check-in date. Late cancellations incur a 1-night charge.",
        "question_ta": "முன்பதிவு ரத்து செய்வதற்கான விதிகள் என்ன?",
        "answer_ta": "செக்-இன் தேதிக்கு 24 மணி நேரத்திற்கு முன்பு வரை நீங்கள் இலவசமாக ரத்து செய்யலாம்.",
    },
    {
        "category": "dining",
        "question_en": "Is breakfast included and when is it served?",
        "answer_en": "Complimentary buffet breakfast is included with Deluxe and Suite bookings, served from 7:00 AM to 10:30 AM at the Sunset Restaurant.",
        "question_ta": "காலை உணவு இலவசமா மற்றும் எந்த நேரத்தில் கிடைக்கும்?",
        "answer_ta": "டீலக்ஸ் மற்றும் சூட் அறைகளுக்கு இலவச காலை உணவு உண்டு. காலை 7:00 மணி முதல் 10:30 மணி வரை கிடைக்கும்.",
    },
    {
        "category": "facilities",
        "question_en": "Do you provide parking and Wi-Fi?",
        "answer_en": "Yes, we provide complimentary high-speed Wi-Fi and 24-hour valet parking for all registered hotel guests.",
        "question_ta": "பார்க்கிங் மற்றும் வைஃபை வசதி உள்ளதா?",
        "answer_ta": "ஆம், அனைத்து விருந்தினர்களுக்கும் இலவச அதிவேக வைஃபை மற்றும் 24 மணி நேர இலவச பார்க்கிங் வசதி உண்டு.",
    },
]


def seed_database(db: Session = None) -> None:
    init_db()
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Seed rooms if table empty
        if db.query(Room).count() == 0:
            print("Seeding hotel rooms...")
            for data in ROOMS_DATA:
                vec = embed_text(f"{data['name']} {data['description']} {data['type']}")
                room = Room(
                    room_number=data["room_number"],
                    name=data["name"],
                    type=data["type"],
                    floor=data["floor"],
                    max_guests=data["max_guests"],
                    price_per_night=data["price_per_night"],
                    amenities=data["amenities"],
                    description=data["description"],
                    description_ta=data["description_ta"],
                    description_vector=vec,
                    is_active=True,
                )
                db.add(room)
            db.commit()
            print(f"Successfully seeded {len(ROOMS_DATA)} rooms.")

        # Seed FAQs if table empty
        if db.query(FAQ).count() == 0:
            print("Seeding hotel FAQs...")
            for data in FAQS_DATA:
                vec = embed_text(f"{data['question_en']} {data['answer_en']}")
                faq = FAQ(
                    category=data["category"],
                    question_en=data["question_en"],
                    answer_en=data["answer_en"],
                    question_ta=data["question_ta"],
                    answer_ta=data["answer_ta"],
                    embedding=vec,
                )
                db.add(faq)
            db.commit()
            print(f"Successfully seeded {len(FAQS_DATA)} FAQs.")

    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    seed_database()
