"""Streaming provider clients.

Each client is a thin, dependency-light wrapper that streams to/from a single
provider and is safe to share across sessions (it manages its own per-stream
state). The LiveKit agent worker wraps these as framework plugins; the REST
layer can also exercise them directly for smoke tests.
"""
