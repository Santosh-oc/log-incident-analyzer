"""LLM provider abstraction."""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Run a chat completion and return the raw assistant text.

        Raises LLMError with a readable message on any failure.
        """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model identifier used for completions."""


class LLMError(Exception):
    """Readable LLM failure. Never contains credentials."""
