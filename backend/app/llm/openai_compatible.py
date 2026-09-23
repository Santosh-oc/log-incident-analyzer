"""OpenAI-compatible chat completions provider (e.g. vLLM serving Qwen)."""
import httpx

from app.config import get_settings
from app.llm.provider import LLMError, LLMProvider

_SNIPPET_LIMIT = 300


def _snippet(raw: str) -> str:
    raw = raw.strip()
    if len(raw) > _SNIPPET_LIMIT:
        return raw[:_SNIPPET_LIMIT] + "…"
    return raw


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.llm_base_url.rstrip("/")
        self._model = settings.llm_model
        self._api_key = settings.llm_api_key
        self._timeout = settings.llm_timeout_seconds
        self._max_tokens = settings.llm_max_tokens

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": self._max_tokens,
        }
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise LLMError(
                f"LLM request timed out after {self._timeout:.0f}s. "
                "Check that the model server is running and responsive."
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Could not reach the LLM endpoint at {self._base_url}: {exc.__class__.__name__}. "
                "Check LLM_BASE_URL and that the server is up."
            ) from exc

        if response.status_code == 401:
            raise LLMError(
                "LLM endpoint rejected the API key (401 Unauthorized). "
                "Check LLM_API_KEY in .env."
            )
        if response.status_code == 429:
            raise LLMError(
                "LLM endpoint is rate-limited (429). Try again shortly."
            )
        if response.status_code >= 500:
            raise LLMError(
                f"LLM server error ({response.status_code}). "
                f"Response: {_snippet(response.text) or '<empty>'}"
            )
        if response.status_code >= 400:
            raise LLMError(
                f"LLM request failed ({response.status_code}). "
                f"Response: {_snippet(response.text) or '<empty>'}"
            )

        try:
            body = response.json()
        except ValueError:
            raise LLMError(
                "LLM endpoint returned a non-JSON response. "
                f"Response: {_snippet(response.text) or '<empty>'}"
            ) from None

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMError(
                "LLM response had no choices[0].message.content. "
                f"Response: {_snippet(response.text) or '<empty>'}"
            ) from None
        if not isinstance(content, str) or not content.strip():
            raise LLMError(
                "LLM returned an empty response. "
                f"Response: {_snippet(response.text) or '<empty>'}"
            )
        return content
