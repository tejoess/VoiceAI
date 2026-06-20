"""Incremental sentence/clause chunking for streaming TTS.

TTS sounds best when fed coherent clauses, but we must NOT wait for a whole
response.  Two mechanisms ensure audio starts within the first few LLM words:

1. Hard boundaries (.!?।॥\\n) flush the buffer immediately.
2. Soft boundaries (,;:—) flush once the buffer is >= _MIN_SOFT_LEN chars.
3. First-chunk deadline: if _FIRST_CHUNK_MAX chars accumulate without any
   boundary, we force a flush at the last word boundary.  This guarantees TTS
   kicks off within ~5-6 LLM words even on punctuation-free responses.
"""

from __future__ import annotations

# Hard boundaries → flush immediately (sentence endings)
_HARD = ".!?।॥\n"
# Soft boundaries → flush once enough text has accumulated
_SOFT = ",;:—"
# Flush at a soft boundary once this many chars are buffered.
# 4 means "Sure," (comma at index 4) triggers immediately — ideal for voice.
_MIN_SOFT_LEN = 3   # "Yes," (3 chars before comma) now flushes immediately
# Maximum chars to accumulate before forcing TTS kickoff (first chunk only).
# 15 chars ≈ 3 words — TTS starts within the first short phrase every time.
_FIRST_CHUNK_MAX = 15


class SentenceAggregator:
    def __init__(self, min_soft_len: int = _MIN_SOFT_LEN):
        self._buf: str = ""
        self._min_soft_len = min_soft_len
        self._first_flushed: bool = False

    def push(self, text: str) -> list[str]:
        """Add LLM token delta; return any clause chunks ready for TTS."""
        self._buf += text
        out: list[str] = []

        while True:
            idx = self._find_boundary(self._buf)

            if idx is not None:
                # Natural boundary found — flush up to and including it.
                chunk = self._buf[: idx + 1].strip()
                self._buf = self._buf[idx + 1 :]
                if chunk:
                    out.append(chunk)
                    self._first_flushed = True

            elif not self._first_flushed and len(self._buf) >= _FIRST_CHUNK_MAX:
                # No boundary yet but buffer is large — force flush at the last
                # word boundary so TTS starts immediately instead of waiting for
                # the first sentence to complete.
                last_space = self._buf.rfind(" ")
                if last_space > 0:
                    chunk = self._buf[:last_space].strip()
                    self._buf = self._buf[last_space + 1 :]
                else:
                    chunk = self._buf.strip()
                    self._buf = ""
                if chunk:
                    out.append(chunk)
                    self._first_flushed = True
                break

            else:
                break

        return out

    def _find_boundary(self, s: str) -> int | None:
        for i, ch in enumerate(s):
            if ch in _HARD:
                return i
            if ch in _SOFT and i >= self._min_soft_len:
                return i
        return None

    def flush(self) -> str | None:
        """Return whatever remains (call at end of LLM stream)."""
        chunk = self._buf.strip()
        self._buf = ""
        self._first_flushed = False  # reset for reuse
        return chunk or None
