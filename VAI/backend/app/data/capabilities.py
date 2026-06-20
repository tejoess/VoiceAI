"""Capability catalog.

A capability is a toggle on an agent that (a) contributes an instruction block
to the Capabilities prompt layer and (b) may expose tools to the LLM. Some
capabilities are fully realtime today; others (RAG, CRM) are scaffolded with a
clear interface and marked ``status="planned"`` so the UI can show them as
"coming soon" without breaking prompt construction.
"""

from __future__ import annotations

CAPABILITIES: dict[str, dict] = {
    "faqs": {
        "id": "faqs",
        "name": "Answer FAQs",
        "status": "available",
        "prompt": (
            "Answer frequently asked questions accurately using your configured "
            "knowledge. If you are unsure, say so honestly rather than guessing."
        ),
        "tools": [],
    },
    "documents": {
        "id": "documents",
        "name": "Upload Documents (RAG)",
        "status": "available",
        "prompt": (
            "When relevant knowledge from uploaded documents is provided, ground "
            "your answer in it. If the caller asks about topics that may be in "
            "the documents, call `search_knowledge_base` to look it up first."
        ),
        "tools": ["search_knowledge_base"],
    },
    "human_handoff": {
        "id": "human_handoff",
        "name": "Human Handoff",
        "status": "available",
        "prompt": (
            "If the caller asks for a human, is frustrated, or the request is "
            "outside your scope, offer to transfer to a human agent and call "
            "the `request_human_handoff` tool."
        ),
        "tools": ["request_human_handoff"],
    },
    "tool_calling": {
        "id": "tool_calling",
        "name": "Tool Calling",
        "status": "available",
        "prompt": (
            "You can call tools to take actions. Only call a tool when it is "
            "clearly needed, and tell the caller what you're doing in one short "
            "sentence."
        ),
        "tools": [],
    },
    "lead_collection": {
        "id": "lead_collection",
        "name": "Lead Collection",
        "status": "available",
        "prompt": (
            "Naturally collect the caller's name, phone number, and reason for "
            "calling. Confirm each detail back. When you have them, call the "
            "`save_lead` tool. Do not interrogate — gather details in the flow "
            "of conversation."
        ),
        "tools": ["save_lead"],
    },
    "appointment_booking": {
        "id": "appointment_booking",
        "name": "Appointment Booking",
        "status": "available",
        "prompt": (
            "Help the caller book an appointment. Collect the preferred date, "
            "time, and service, confirm availability, then call the "
            "`book_appointment` tool. Always read back the final details."
        ),
        "tools": ["book_appointment"],
    },
    "webhook": {
        "id": "webhook",
        "name": "Webhook Support",
        "status": "available",
        "prompt": (
            "Significant events during this call are delivered to the business's "
            "systems automatically; you do not need to mention this to the caller."
        ),
        "tools": ["trigger_webhook"],
    },
    "crm": {
        "id": "crm",
        "name": "CRM Integration",
        "status": "planned",
        "prompt": (
            "Caller records may be synced to the business CRM. Use any provided "
            "CRM context to personalize the conversation."
        ),
        "tools": [],
    },
}

DEFAULT_CAPABILITIES = ["faqs"]


def get_capability(cap_id: str) -> dict | None:
    return CAPABILITIES.get(cap_id)


def list_capabilities() -> list[dict]:
    return list(CAPABILITIES.values())


def tools_for_capabilities(cap_ids: list[str]) -> list[str]:
    tools: list[str] = []
    for cid in cap_ids:
        cap = CAPABILITIES.get(cid)
        if cap:
            tools.extend(cap["tools"])
    # de-dup, preserve order
    seen: set[str] = set()
    return [t for t in tools if not (t in seen or seen.add(t))]
