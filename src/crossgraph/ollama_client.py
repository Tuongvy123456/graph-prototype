import httpx
from pydantic import ValidationError
from .schemas import Extraction


class OllamaExtractionError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, host: str, model: str, timeout: float, num_ctx: int, think: bool = False):
        self.host, self.model, self.timeout, self.num_ctx, self.think = host.rstrip("/"), model, timeout, num_ctx, think

    def extract(self, prompt: str) -> Extraction:
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "stream": False, "think": self.think, "format": Extraction.model_json_schema(), "options": {"temperature": 0, "num_ctx": self.num_ctx}}
        last_error = None
        for _ in range(2):
            try:
                response = httpx.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                content = data["message"]["content"]
                try:
                    return Extraction.model_validate_json(content)
                except ValidationError as exc:
                    detail = exc.errors()[0]["msg"]
                    last_error = f"{detail}; done_reason={data.get('done_reason')!r}; content_chars={len(content)}"
            except (httpx.HTTPError, KeyError, ValueError, ValidationError) as exc:
                last_error = str(exc)
        raise OllamaExtractionError(f"Ollama extraction failed after 2 attempts: {last_error}")
