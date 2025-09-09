import os
from typing import Optional

from browser_use import ChatOpenAI


def get_openrouter_llm(api_key: Optional[str] = None, model: Optional[str] = None) -> ChatOpenAI:
    """Return a ChatOpenAI configured for OpenRouter.

    Uses dotenvx-loaded env var `OPENROUTER_API_KEY` and optional `OPENROUTER_MODEL`.
    If not present, falls back to a blank secret string ("") and default model
    "x-ai/grok-4". To load encrypted .env values at runtime, run your command via
    `dotenvx run -- uv run ...` so the environment is populated.
    """

    # Prefer explicit argument, else environment (loaded by dotenvx), else blank/defaults
    openrouter_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model = model or os.getenv("OPENROUTER_MODEL", "x-ai/grok-4")
    return ChatOpenAI(
        model=openrouter_model,
        base_url="https://openrouter.ai/api/v1",
        api_key=openrouter_key,
    )
