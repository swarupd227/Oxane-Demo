"""Each client's policy, and the guard that enforces it on every model call.

The desk serves more than one client. Data, mapping memory and model use never cross from one
client to another, and a client that does not permit AI stays on the existing process: its
facilities run on code checks only. The guard refuses any model request that carries such a
client's names, so a slip in the pipeline fails loudly instead of sending its data.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from app.pipeline.gateway import Gateway, Schema


class ModelNotPermitted(RuntimeError):
    """A model call would have carried data from a client that does not permit AI."""


def clients(record: dict[str, Any]) -> list[dict[str, Any]]:
    return record["clients"]


def client_of(record: dict[str, Any], facility_id: str) -> dict[str, Any]:
    owner = next(f["client"] for f in record["facilities"] if f["id"] == facility_id)
    return next(c for c in record["clients"] if c["id"] == owner)


def facilities_of(record: dict[str, Any], client_id: str) -> list[dict[str, Any]]:
    return [f for f in record["facilities"] if f["client"] == client_id]


def ai_permitted(record: dict[str, Any], facility_id: str) -> bool:
    return bool(client_of(record, facility_id)["ai_permitted"])


def protected_names(record: dict[str, Any]) -> list[str]:
    """Words that identify a no-AI client's data: its name and its facilities' names."""
    names = []
    for client in record["clients"]:
        if client["ai_permitted"]:
            continue
        names.append(client["name"].split()[0])
        for facility in facilities_of(record, client["id"]):
            names += [facility["name"].split()[0], facility.get("borrower", facility["name"])]
    return names


@dataclass
class GuardedGateway:
    """One client's way to the model. For a client that does not permit AI every call is
    refused; for any client, a request carrying a protected client's names is refused."""

    gateway: Gateway
    client: dict[str, Any]
    protected: list[str]
    calls: list[Any] = field(default_factory=list)

    def parse(self, task: str, system: str, content: list[dict[str, Any]],
              schema: type[Schema], max_tokens: int = 32000) -> Schema:
        if not self.client["ai_permitted"]:
            raise ModelNotPermitted(f"{self.client['name']} does not permit AI ({task})")
        text = json.dumps(content).lower()
        hits = [name for name in self.protected if name.lower() in text]
        if hits:
            raise ModelNotPermitted(f"{task} would send data about {hits[0]}, whose client does "
                                    "not permit AI")
        before = len(self.gateway.usage)
        parsed = self.gateway.parse(task, system, content, schema, max_tokens)
        self.calls += self.gateway.usage[before:]
        return parsed

    @property
    def model(self) -> str:
        return self.gateway.model


def guarded(gateway: Gateway, record: dict[str, Any]) -> dict[str, GuardedGateway]:
    protected = protected_names(record)
    return {c["id"]: GuardedGateway(gateway, c, protected) for c in record["clients"]}


def usage_by_client(gateways: dict[str, GuardedGateway]) -> list[dict[str, Any]]:
    return [
        {
            "client": client_id,
            "ai_permitted": g.client["ai_permitted"],
            "calls": len(g.calls),
            "tokens": sum(u.input_tokens + u.output_tokens + u.cache_read_tokens
                          + u.cache_write_tokens for u in g.calls),
            "cost_usd": round(sum(u.cost_usd(g.model) for u in g.calls), 4),
        }
        for client_id, g in gateways.items()
    ]
