"""LLM service for generating book summaries.

Wraps the OpenAI API with:
- A focused summarization prompt
- Semaphore-based concurrency control to prevent rate-limit exhaustion
- FastAPI dependency injection for clean testability

The service is injected via `get_llm_service` so tests can override it
with a mock without touching any business logic.
"""

import asyncio
import logging

from openai import AsyncOpenAI

from src.settings import settings

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM_PROMPT = (
    "You are a helpful bookstore assistant. Generate a concise, engaging summary "
    "of the following book text that helps customers decide whether to read it. "
    "The summary must be exactly 2-3 short paragraphs (150-250 words total), "
    "written for a general audience. Focus on the main themes, plot overview "
    "(without major spoilers), and what makes the book compelling. "
    "Do not include any preamble — start directly with the summary."
)


class LLMService:
    """Manages LLM interactions with concurrency control."""

    def __init__(self, client: AsyncOpenAI, model: str, max_concurrent: int) -> None:
        self._client = client
        self._model = model
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def generate_summary(self, text: str) -> str:
        """Generate a book summary from full text, respecting concurrency limits."""
        async with self._semaphore:
            logger.info("Generating summary (model=%s)", self._model)
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                temperature=0.7,
                max_tokens=512,
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("LLM returned empty content")
            summary = content.strip()
            logger.info("Summary generated (%d chars)", len(summary))
            return summary


# Module-level singleton — reuses the HTTP connection pool across requests.
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """FastAPI dependency that provides the LLM service.

    Returns a singleton instance so the OpenAI client's connection pool
    and the concurrency semaphore are shared across all requests.
    """
    global _llm_service
    if _llm_service is None:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        _llm_service = LLMService(
            client=client,
            model=settings.OPENAI_MODEL,
            max_concurrent=settings.LLM_MAX_CONCURRENT_REQUESTS,
        )
    return _llm_service
