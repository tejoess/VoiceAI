"""Seed a default business + a couple of sample agents.

Run: ``python -m app.scripts.seed``  (requires Postgres reachable).
Idempotent-ish: it skips seeding if any agents already exist.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.core.database import create_all, dispose_engine, get_sessionmaker
from app.core.logging import get_logger
from app.models.agent import Agent
from app.models.business import Business
from app.services import registry
from app.voice.templates import warm_templates

log = get_logger(__name__)


async def seed() -> None:
    warm_templates()
    registry.warm_catalogs()
    await create_all()

    sm = get_sessionmaker()
    async with sm() as db:
        existing = (await db.execute(select(func.count()).select_from(Agent))).scalar_one()
        if existing:
            log.info("seed.skip", reason="agents already exist", count=existing)
            return

        biz = Business(
            name="Acme Clinics",
            description="A multi-city diagnostics & doctor-appointment chain.",
            context=(
                "Acme Clinics offers blood tests, scans, and doctor consultations "
                "across Mumbai, Pune, and Bengaluru. Hours are 8am–9pm daily. "
                "Reports are delivered within 24 hours."
            ),
        )
        db.add(biz)
        await db.flush()

        reception = Agent(
            business_id=biz.id,
            name="Reception Assistant",
            description="Handles inbound calls: FAQs, lead capture, appointment booking.",
            system_prompt=(
                "You are the front-desk assistant for Acme Clinics. Help callers book "
                "appointments, answer questions about tests and timings, and capture "
                "their details. Be efficient and warm."
            ),
            greeting="Namaste! Thank you for calling Acme Clinics. How can I help you today?",
            fallback_message="I'm sorry, I didn't catch that. Could you please say it again?",
            voice_id="sarvam_anushka",
            primary_language="hi",
            languages=["hi", "hinglish", "en", "mr"],
            tone="friendly",
            speaking_style="conversational",
            capabilities=["faqs", "lead_collection", "appointment_booking", "human_handoff"],
        )

        sales = Agent(
            business_id=biz.id,
            name="Sales Qualifier",
            description="Qualifies inbound product interest in English.",
            system_prompt=(
                "You qualify inbound leads for a SaaS product. Understand the caller's "
                "use case, gather their details, and book a demo for interested buyers."
            ),
            greeting="Hi there! Thanks for your interest. Mind if I ask a couple of quick questions?",
            fallback_message="Sorry, could you repeat that for me?",
            voice_id="cartesia_isha",
            primary_language="en",
            languages=["en"],
            tone="professional",
            speaking_style="persuasive",
            capabilities=["faqs", "lead_collection", "appointment_booking", "webhook"],
        )

        db.add_all([reception, sales])
        await db.commit()
        log.info("seed.done", business=biz.name, agents=2)


async def _main() -> None:
    try:
        await seed()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
