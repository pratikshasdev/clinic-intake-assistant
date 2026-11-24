"""Two interchangeable FHIR backends: a real R4 server over HTTP, or an in-memory store.

The in-memory store implements just enough of FHIR's REST behaviour for this
app (transactions with urn:uuid references, read, update, and the few search
parameters we use) so tests and offline demos need no server.
"""

from __future__ import annotations

import copy
import itertools
import json
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from .fhir_ids import DEMO_TAG


class FhirError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, outcome: Any = None):
        super().__init__(message)
        self.status = status
        self.outcome = outcome


class FhirStore(Protocol):
    base_url: str

    async def transaction(self, bundle: dict) -> list[str]:
        """Post a transaction Bundle; return the 'Type/id' of each entry in order."""

    async def read(self, resource_type: str, resource_id: str) -> dict: ...

    async def update(self, resource: dict) -> dict: ...

    async def create(self, resource: dict) -> dict: ...

    async def search(self, resource_type: str, params: dict[str, str]) -> list[dict]: ...

    async def aclose(self) -> None: ...


def demo_tag_param() -> str:
    return f"{DEMO_TAG['system']}|{DEMO_TAG['code']}"


class HttpFhirStore:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Accept": "application/fhir+json", "Content-Type": "application/fhir+json"},
        )

    async def _send(self, method: str, url: str, **kwargs: Any) -> dict:
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise FhirError(f"Could not reach the FHIR server at {self.base_url}: {exc}") from exc
        if response.status_code >= 400:
            try:
                outcome = response.json()
            except ValueError:
                outcome = response.text[:500]
            raise FhirError(f"FHIR {method} {url} failed with {response.status_code}", response.status_code, outcome)
        return response.json() if response.content else {}

    async def transaction(self, bundle: dict) -> list[str]:
        result = await self._send("POST", "", content=json.dumps(bundle))
        refs = []
        for entry in result.get("entry", []):
            location = entry.get("response", {}).get("location", "")
            # e.g. "Patient/123/_history/1"
            parts = location.split("/")
            refs.append(f"{parts[0]}/{parts[1]}" if len(parts) >= 2 else location)
        return refs

    async def read(self, resource_type: str, resource_id: str) -> dict:
        return await self._send("GET", f"{resource_type}/{resource_id}")

    async def update(self, resource: dict) -> dict:
        return await self._send("PUT", f"{resource['resourceType']}/{resource['id']}", content=json.dumps(resource))

    async def create(self, resource: dict) -> dict:
        return await self._send("POST", resource["resourceType"], content=json.dumps(resource))

    async def search(self, resource_type: str, params: dict[str, str]) -> list[dict]:
        # HAPI reuses cached search results for a minute by default; a front
        # desk dashboard needs fresh results, so opt out per request.
        bundle = await self._send("GET", resource_type, params=params, headers={"Cache-Control": "no-cache"})
        resources = [e["resource"] for e in bundle.get("entry", []) if "resource" in e]
        return [r for r in resources if r.get("resourceType") == resource_type]

    async def aclose(self) -> None:
        await self._client.aclose()


class MemoryFhirStore:
    base_url = "memory"

    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict]] = {}
        self._ids = itertools.count(1)

    def _stamp(self, resource: dict) -> dict:
        meta = resource.setdefault("meta", {})
        version = int(meta.get("versionId", "0")) + 1
        meta["versionId"] = str(version)
        meta["lastUpdated"] = datetime.now(timezone.utc).isoformat()
        return resource

    async def transaction(self, bundle: dict) -> list[str]:
        if bundle.get("type") != "transaction":
            raise FhirError("Only transaction bundles are supported", 400)
        entries = copy.deepcopy(bundle.get("entry", []))
        mapping: dict[str, str] = {}
        for entry in entries:
            rtype = entry["resource"]["resourceType"]
            new_id = str(next(self._ids))
            mapping[entry["fullUrl"]] = f"{rtype}/{new_id}"
            entry["resource"]["id"] = new_id

        def rewrite(node: Any) -> Any:
            if isinstance(node, dict):
                return {
                    k: (mapping.get(v, v) if k == "reference" and isinstance(v, str) else rewrite(v))
                    for k, v in node.items()
                }
            if isinstance(node, list):
                return [rewrite(v) for v in node]
            return node

        refs = []
        for entry in entries:
            resource = self._stamp(rewrite(entry["resource"]))
            self._data.setdefault(resource["resourceType"], {})[resource["id"]] = resource
            refs.append(f"{resource['resourceType']}/{resource['id']}")
        return refs

    async def read(self, resource_type: str, resource_id: str) -> dict:
        try:
            return copy.deepcopy(self._data[resource_type][resource_id])
        except KeyError:
            raise FhirError(f"{resource_type}/{resource_id} not found", 404) from None

    async def update(self, resource: dict) -> dict:
        existing = await self.read(resource["resourceType"], resource["id"])
        resource = copy.deepcopy(resource)
        resource.setdefault("meta", {})["versionId"] = existing["meta"]["versionId"]
        stored = self._stamp(resource)
        self._data[resource["resourceType"]][resource["id"]] = stored
        return copy.deepcopy(stored)

    async def create(self, resource: dict) -> dict:
        resource = copy.deepcopy(resource)
        resource["id"] = str(next(self._ids))
        stored = self._stamp(resource)
        self._data.setdefault(resource["resourceType"], {})[resource["id"]] = stored
        return copy.deepcopy(stored)

    async def search(self, resource_type: str, params: dict[str, str]) -> list[dict]:
        results = list(self._data.get(resource_type, {}).values())

        def has_tag(r: dict, token: str) -> bool:
            system, _, code = token.partition("|")
            return any(t.get("system") == system and t.get("code") == code for t in r.get("meta", {}).get("tag", []))

        def ref_matches(r: dict, fields: tuple[str, ...], value: str) -> bool:
            return any((r.get(f) or {}).get("reference") == value for f in fields)

        for key, value in params.items():
            if key == "_tag":
                results = [r for r in results if has_tag(r, value)]
            elif key == "_id":
                ids = set(value.split(","))
                results = [r for r in results if r["id"] in ids]
            elif key == "status":
                allowed = set(value.split(","))
                results = [r for r in results if r.get("status") in allowed]
            elif key in ("patient", "subject"):
                results = [r for r in results if ref_matches(r, ("patient", "subject"), value)]
            elif key == "_lastUpdated" and value.startswith("ge"):
                cutoff = datetime.fromisoformat(value[2:].replace("Z", "+00:00"))
                results = [r for r in results if datetime.fromisoformat(r["meta"]["lastUpdated"]) >= cutoff]
            elif key == "family":
                results = [r for r in results if any(n.get("family", "").lower() == value.lower() for n in r.get("name", []))]
            elif key == "given":
                results = [
                    r for r in results
                    if any(value.lower() in [g.lower() for g in n.get("given", [])] for n in r.get("name", []))
                ]
            elif key == "birthdate":
                results = [r for r in results if r.get("birthDate") == value]
            elif key in ("_sort", "_count", "_elements"):
                continue
            else:
                raise FhirError(f"MemoryFhirStore does not support search parameter {key!r}", 400)

        if params.get("_sort", "").lstrip("-") == "_lastUpdated":
            results.sort(key=lambda r: r["meta"]["lastUpdated"], reverse=params["_sort"].startswith("-"))
        if "_count" in params:
            results = results[: int(params["_count"])]
        return copy.deepcopy(results)

    async def aclose(self) -> None:
        return None


def make_store(base_url: str) -> FhirStore:
    if base_url == "memory":
        return MemoryFhirStore()
    return HttpFhirStore(base_url)
