"""OpenAI LLM provider."""

import base64
from pathlib import Path
from typing import Optional

from openai import OpenAI

from peer.llm.base import LLMProvider, LLMResponse

# Pricing per 1M tokens (as of late 2024)
PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
}


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        vision_model: str = "gpt-4o",
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.vision_model = vision_model

    @property
    def name(self) -> str:
        return "openai"

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate a text completion using OpenAI."""
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
        )

        usage = response.usage
        cost = self._calculate_cost(
            self.model,
            usage.prompt_tokens,
            usage.completion_tokens,
        )

        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=self.model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost=cost,
        )

    def analyze_image(
        self,
        image_path: Path,
        prompt: str,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Analyze an image using GPT-4 Vision."""
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

        response = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_data}",
                                "detail": "low",
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_tokens=max_tokens,
        )

        usage = response.usage
        cost = self._calculate_cost(
            self.vision_model,
            usage.prompt_tokens,
            usage.completion_tokens,
        )

        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=self.vision_model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost=cost,
        )

    def _calculate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Calculate cost for a request."""
        pricing = PRICING.get(model, PRICING["gpt-4o-mini"])

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost
