"""LLM integration for Peer."""

from peer.llm.base import LLMProvider, LLMResponse
from peer.llm.cost import CostTracker

_provider_instance = None


def get_provider() -> LLMProvider:
    """Get the configured LLM provider."""
    global _provider_instance

    if _provider_instance is None:
        from peer.config import get_config

        config = get_config()

        # Try OpenAI first, then Anthropic
        if config.openai_api_key:
            from peer.llm.openai_provider import OpenAIProvider

            _provider_instance = OpenAIProvider(config.openai_api_key)
        elif config.anthropic_api_key:
            from peer.llm.anthropic_provider import AnthropicProvider

            _provider_instance = AnthropicProvider(config.anthropic_api_key)
        else:
            raise ValueError(
                "No LLM API key configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."
            )

    return _provider_instance


__all__ = ["LLMProvider", "LLMResponse", "CostTracker", "get_provider"]
