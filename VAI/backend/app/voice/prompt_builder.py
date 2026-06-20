"""Layered prompt construction.

The system prompt is assembled from ordered layers so each concern lives in
exactly one place and can be tuned independently:

    1. Global Prompt          — voice-channel rules (platform-wide)
    2. Business Prompt         — company name / context
    3. Agent Prompt            — the agent's own system prompt
    4. Tone Prompt             — attitude
    5. Language Prompt         — which language to speak + how
    6. Capabilities Prompt     — enabled features and their behavior
    7. (Greeting / Fallback)   — surfaced so the model stays consistent
    8. Future RAG Context      — retrieved knowledge (when available)

Conversation History and Current User Input are NOT part of the system prompt;
they are appended as separate chat messages by ``build_messages`` so streaming
LLM calls keep the system prompt cacheable and stable across turns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.data import capabilities as cap_data
from app.data import languages as lang_data
from app.data import speaking_styles as style_data
from app.data import tones as tone_data
from app.voice.templates import global_prompt


@dataclass
class AgentPromptConfig:
    """Minimal projection of an agent needed to build prompts.

    Kept as a plain dataclass (not the ORM model) so it can be cached as JSON
    and reconstructed on the realtime path without a DB round-trip.
    """

    name: str
    system_prompt: str = ""
    greeting: str = ""
    fallback_message: str = ""
    tone: str = "friendly"
    speaking_style: str = "conversational"
    primary_language: str = "en"
    languages: list[str] = field(default_factory=lambda: ["en"])
    capabilities: list[str] = field(default_factory=list)
    business_name: str | None = None
    business_context: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "AgentPromptConfig":
        return cls(
            name=d.get("name", "Assistant"),
            system_prompt=d.get("system_prompt", "") or "",
            greeting=d.get("greeting", "") or "",
            fallback_message=d.get("fallback_message", "") or "",
            tone=d.get("tone", "friendly"),
            speaking_style=d.get("speaking_style", "conversational"),
            primary_language=d.get("primary_language", "en"),
            languages=d.get("languages") or [d.get("primary_language", "en")],
            capabilities=d.get("capabilities") or [],
            business_name=d.get("business_name"),
            business_context=d.get("business_context"),
        )


def _business_layer(cfg: AgentPromptConfig) -> str | None:
    if not cfg.business_name and not cfg.business_context:
        return None
    parts = []
    if cfg.business_name:
        parts.append(f"You represent {cfg.business_name}.")
    if cfg.business_context:
        parts.append(cfg.business_context.strip())
    return "Business context:\n" + " ".join(parts)


def _agent_layer(cfg: AgentPromptConfig) -> str | None:
    body = cfg.system_prompt.strip()
    header = f"Your role: You are {cfg.name}."
    return f"{header}\n{body}" if body else header


def _tone_layer(cfg: AgentPromptConfig) -> str | None:
    tone = tone_data.get_tone(cfg.tone)
    style = style_data.get_style(cfg.speaking_style)
    parts = []
    if tone:
        parts.append(tone["prompt"])
    if style:
        parts.append(style["prompt"])
    return "Tone and delivery:\n" + " ".join(parts) if parts else None


def _language_layer(cfg: AgentPromptConfig, active_language: str) -> str | None:
    lang = lang_data.get_language(active_language)
    if not lang:
        return None
    lines = [f"Speak in {lang['name']}. {lang['prompt_hint']}"]
    others = [c for c in cfg.languages if c != active_language]
    if others:
        names = ", ".join(
            (lang_data.get_language(c) or {}).get("name", c) for c in others
        )
        lines.append(
            f"If the caller clearly switches to one of these languages, you may "
            f"follow them: {names}."
        )
    return "Language:\n" + " ".join(lines)


def _capabilities_layer(cfg: AgentPromptConfig) -> str | None:
    if not cfg.capabilities:
        return None
    blocks = []
    for cid in cfg.capabilities:
        cap = cap_data.get_capability(cid)
        if cap and cap.get("prompt"):
            blocks.append(f"- {cap['name']}: {cap['prompt']}")
    if not blocks:
        return None
    return "Your capabilities:\n" + "\n".join(blocks)


def _greeting_fallback_layer(cfg: AgentPromptConfig) -> str | None:
    parts = []
    if cfg.greeting:
        parts.append(f'Your opening greeting is: "{cfg.greeting.strip()}"')
    if cfg.fallback_message:
        parts.append(
            f'When you cannot help or something goes wrong, fall back to: '
            f'"{cfg.fallback_message.strip()}"'
        )
    return "\n".join(parts) if parts else None


def build_system_prompt(
    cfg: AgentPromptConfig,
    active_language: str | None = None,
    rag_context: str | None = None,
) -> str:
    """Assemble the full layered system prompt for a turn."""
    active_language = active_language or cfg.primary_language

    layers: list[str | None] = [
        global_prompt(),
        _business_layer(cfg),
        _agent_layer(cfg),
        _tone_layer(cfg),
        _language_layer(cfg, active_language),
        _capabilities_layer(cfg),
        _greeting_fallback_layer(cfg),
    ]

    if rag_context:  # Future RAG layer
        layers.append("Relevant knowledge (use if helpful):\n" + rag_context.strip())

    return "\n\n".join(layer for layer in layers if layer)


def build_messages(
    cfg: AgentPromptConfig,
    history: list[dict],
    user_input: str | None = None,
    active_language: str | None = None,
    rag_context: str | None = None,
) -> list[dict]:
    """Produce the OpenAI-style message list for a streaming completion.

    ``history`` is a list of ``{"role": "user"|"assistant", "content": str}``.
    ``user_input`` is the latest (possibly partial-finalized) user utterance;
    pass ``None`` to generate the opening greeting turn.
    """
    messages: list[dict] = [
        {
            "role": "system",
            "content": build_system_prompt(cfg, active_language, rag_context),
        }
    ]
    messages.extend(history)
    if user_input is not None:
        messages.append({"role": "user", "content": user_input})
    return messages
