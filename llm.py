"""Tiny OpenAI-compatible chat client (OpenRouter, xAI, or Ollama)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import config

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self) -> None:
        self.backend = (config.LLM_BACKEND or "openrouter").lower()
        self.model = config.LLM_MODEL or "qwen/qwen3.7-flash"
        self.api_key = config.llm_api_key()
        self.base_url = config.llm_base_url().rstrip("/")
        self._client: Optional[Any] = None

    @property
    def configured(self) -> bool:
        if self.backend == "ollama":
            return True
        return bool(self.api_key)

    async def _http(self) -> Any:
        if httpx is None:
            raise LLMError("httpx is not installed")
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=90.0)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        *,
        max_tokens: int = 800,
    ) -> Dict[str, Any]:
        if not self.configured:
            raise LLMError("LLM not configured (OPENROUTER_API_KEY / XAI_API_KEY)")

        url = f"{self.base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.backend == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/danielvegac/tesla-bot"
            headers["X-Title"] = "Tesla Familia Bot"

        client = await self._http()
        try:
            response = await client.post(url, json=payload, headers=headers)
        except Exception as exc:
            raise LLMError(f"LLM network error: {exc}") from exc

        if response.status_code >= 400:
            raise LLMError(
                f"LLM HTTP {response.status_code}: {response.text[:400]}"
            )
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"LLM empty choices: {data}")
        message = choices[0].get("message") or {}
        usage = data.get("usage") or {}
        if usage:
            print(
                f"[LLM] model={data.get('model', self.model)} "
                f"tokens={usage.get('total_tokens')} cost={usage.get('cost')}"
            )
        return message
