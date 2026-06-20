"""Background workers for all non-realtime work.

Anything that must not block the audio path — webhook delivery, lead/CRM sync,
appointment persistence, transcript + metrics storage — is enqueued to Redis
and processed here by a separate worker process (``python -m app.workers.worker``).
"""
