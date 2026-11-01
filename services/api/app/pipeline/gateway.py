"""The only place that talks to a language model.

Modes: `live` calls the model, `record` calls it once and saves the response, and
`replay` uses saved responses only and never touches the network. Each saved
response is keyed by everything that shaped the request, so a changed prompt
can never silently reuse an old answer.
"""

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

Schema = TypeVar("Schema", bound=BaseModel)

# US$ per million tokens: input, output, cache read, cache write.
PRICES = {"claude-opus-5-5": (4.00, 20.00, 0.20, 5.00)}


class ReplayMiss(RuntimeError):
    """Replay was asked for a response that was never recorded."""


class ModelError(RuntimeError):
    """The model did not return a complete answer."""


@dataclass(frozen=True)
class Usage:
    task: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    from_replay: bool = False
    seconds: float = 0.0

    def cost_usd(self, model: str) -> float:
        rates = PRICES.get(model)
        if rates is None:
            return 0.0
        spent = (self.input_tokens, self.output_tokens, self.cache_read_tokens,
                 self.cache_write_tokens)
        return sum(tokens * rate for tokens, rate in zip(spent, rates, strict=True)) / 1_000_000


class ModelClient(Protocol):
    def request(self, payload: dict[str, Any]) -> tuple[str, Usage]: ...


class AnthropicClient:
    """Claude through the first-party API or Microsoft Foundry, chosen by configuration."""

    def __init__(self, provider: str) -> None:
        if provider == "foundry":
            from anthropic import AnthropicFoundry

            self._client: Any = AnthropicFoundry()
        else:
            from anthropic import Anthropic

            self._client = Anthropic()

    def request(self, payload: dict[str, Any]) -> tuple[str, Usage]:
        with self._client.messages.stream(**payload) as stream:
            message = stream.get_final_message()
        if message.stop_reason != "end_turn":
            raise ModelError(f"Model stopped early: {message.stop_reason}")
        text = next(block.text for block in message.content if block.type == "text")
        usage = message.usage
        return text, Usage(
            task="",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
        )


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Structured outputs need every object closed, with every property required."""
    def close(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for key in ("title", "default"):
                node.pop(key, None)
            for key, value in node.items():
                # Under these keys the names are the schema's own fields, not annotations.
                if key in ("properties", "$defs"):
                    for child in value.values():
                        close(child)
                else:
                    close(value)
        elif isinstance(node, list):
            for item in node:
                close(item)

    schema = model.model_json_schema()
    close(schema)
    return schema


@dataclass
class Gateway:
    mode: str
    fixtures: Path
    model: str = "claude-opus-5-5"
    effort: str = "high"
    client_factory: Callable[[], ModelClient] | None = None
    usage: list[Usage] = field(default_factory=list)
    used: set[Path] = field(default_factory=set)
    _client: ModelClient | None = None

    def parse(self, task: str, system: str, content: list[dict[str, Any]],
              schema: type[Schema], max_tokens: int = 32000) -> Schema:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": strict_schema(schema)},
            },
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": content}],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        path = self.fixtures / task / f"{digest[:32]}.json"
        self.used.add(path)

        if self.mode != "live" and path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.usage.append(Usage(**{**saved["usage"], "from_replay": True}))
            return schema.model_validate_json(saved["text"])
        if self.mode == "replay":
            raise ReplayMiss(f"No recorded response for {task} ({digest[:12]})")

        if self._client is None:
            if self.client_factory is None:
                raise ModelError("No model client is configured")
            self._client = self.client_factory()
        started = time.perf_counter()
        text, usage = self._client.request(payload)
        usage = Usage(**{**asdict(usage), "task": task,
                         "seconds": round(time.perf_counter() - started, 1)})
        self.usage.append(usage)
        parsed = schema.model_validate_json(text)  # Refuse to save an answer that fails here.
        if self.mode == "record":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"task": task, "model": self.model, "text": text,
                                        "usage": asdict(usage)}, indent=1), encoding="utf-8")
        return parsed

    def prune(self) -> int:
        """Delete recordings this run did not use, left behind by earlier prompts."""
        stale = [path for path in self.fixtures.rglob("*.json") if path not in self.used]
        for path in stale:
            path.unlink()
        return len(stale)

    def total_cost_usd(self) -> float:
        return round(sum(item.cost_usd(self.model) for item in self.usage), 4)
