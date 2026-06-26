"""LiveKit access-token minting + room naming.

Issues a short-lived JWT the browser uses to join a room and talk to the agent
worker. The room name encodes the agent id so the dispatched worker knows which
configuration to load (see ``agent_worker._agent_id_from_room``).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from livekit import api

from app.core.config import settings


def make_room_name(agent_id: uuid.UUID) -> str:
    return f"agent_{agent_id}__{uuid.uuid4().hex[:8]}"


def create_access_token(
    *, room_name: str, identity: str, name: str | None = None, ttl_seconds: int = 3600
) -> str:
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(name or identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_ttl(timedelta(seconds=ttl_seconds))
    )
    return token.to_jwt()
