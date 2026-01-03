"""Anthropic Claude LLM provider."""

import base64
from pathlib import Path
from typing import Optional

from anthropic import Anthropic

from peer.llm.base import LLMProvider, LLMResponse

# Pricing per 1M tokens (as of late 2024)
PRICING = {
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
}


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-haiku-20241022",
        vision_model: str = "claude-3-5-sonnet-20241022",
    ):
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.vision_model = vision_model

    @property
    def name(self) -> str:
        return "anthropic"

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate a text completion using Claude."""
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._calculate_cost(self.model, input_tokens, output_tokens)

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return LLMResponse(
            content=content,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
        )

    def analyze_image(
        self,
        image_path: Path,
        prompt: str,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Analyze an image using Claude Vision."""
        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Determine media type
        suffix = image_path.suffix.lower()
        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(suffix, "image/png")

        response = self.client.messages.create(
            model=self.vision_model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._calculate_cost(self.vision_model, input_tokens, output_tokens)

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return LLMResponse(
            content=content,
            model=self.vision_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
        )

    def _calculate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Calculate cost for a request."""
        pricing = PRICING.get(model, PRICING["claude-3-5-haiku-20241022"])

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost
