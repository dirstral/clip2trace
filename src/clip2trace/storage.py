"""Thin helpers for Sinas state stores + an in-memory fallback for local/demo.

Inside a Sinas function, prefer the preinstalled `sinas` SDK with
`context["access_token"]`. This module gives a minimal requests-based client and
an in-memory stand-in so the core library and tests run without a live instance.
See docs/sinas-setup.md.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Job lifecycle, mirroring schemas.JobStatus. Coarse progress hints per status.
JOB_STATUS_ORDER = [
    "created",
    "analyzing",
    "searching",
    "verifying",
    "ranking",
    "reporting",
    "done",
    "failed",
]
JOB_PROGRESS = {
    "created": 0.0,
    "analyzing": 0.15,
    "searching": 0.4,
    "verifying": 0.6,
    "ranking": 0.8,
    "reporting": 0.9,
    "done": 1.0,
    "failed": 1.0,
}
_JOB_META_FIELDS = (
    "input_video_file_id",
    "video_context",
    "date_hint",
    "language_hint",
    "topic_hint",
)


def build_job_state(
    job_id: str,
    mode: str = "demo",
    *,
    status: str = "created",
    error: Optional[str] = None,
    **metadata: Any,
) -> Dict[str, Any]:
    """Assemble a full job-state dict (schemas.Job shape) with a progress hint."""
    if status not in JOB_PROGRESS:
        status = "created"
    state: Dict[str, Any] = {
        "job_id": job_id,
        "status": status,
        "mode": mode,
        "progress": JOB_PROGRESS[status],
        "error": error,
    }
    for k in _JOB_META_FIELDS:
        state[k] = metadata.get(k)
    return state


def advance_job_state(
    state: Dict[str, Any], status: str, *, error: Optional[str] = None
) -> Dict[str, Any]:
    """Return a copy of `state` moved to `status` (+ progress hint / error)."""
    new = dict(state)
    new["status"] = status
    new["progress"] = JOB_PROGRESS.get(status, new.get("progress", 0.0))
    if error is not None:
        new["error"] = error
    if status == "failed" and error is None and not new.get("error"):
        new["error"] = "job failed"
    return new


# Hardcoded SDK default base URL inside a Sinas worker. The base URL is NOT
# delivered via env/context (the diagnose_runtime probe never saw it); it is the
# `sinas` SDK default. See .claude/skills/sinas-package-author/SKILL.md:327-337 and
# docs/research/runtime-diagnostics.md.
SINAS_RUNTIME_BASE_URL = "http://host.docker.internal:8000"
# Stay under the 100 MB /tmp ceiling (confirmed on via-10) with headroom.
_MAX_STAGED_BYTES = 90 * 1024 * 1024


def resolve_runtime_base_url(context: Optional[Dict[str, Any]] = None) -> str:
    """Best-effort runtime base URL for a function calling back to Sinas.

    Prefers an explicit override (context/env), else the SDK default. Mirrors the
    inline resolution used in the sandboxed `code:` blocks in sinas-package.yaml.
    """
    import os

    context = context or {}
    return (
        context.get("api_url")
        or context.get("base_url")
        or os.environ.get("SINAS_BASE_URL")
        or SINAS_RUNTIME_BASE_URL
    )


def stage_input_file(
    file_id: str,
    context: Optional[Dict[str, Any]] = None,
    *,
    namespace: str = "clip2trace",
    collection: str = "input-videos",
    dest_dir: Optional[str] = None,
    max_bytes: int = _MAX_STAGED_BYTES,
    timeout: float = 120.0,
) -> Optional[str]:
    """Download a collection file to a local path so PyAV/opencv can decode it.

    `file_id` is the file's NAME within the collection — the Sinas files API is
    name-addressed (GET /files/{ns}/{collection}/{name}) and returns a JSON envelope
    `{content_base64, content_type, file_metadata, version}` (not raw bytes), so we
    base64-decode it to a local file. Returns the local path, or None if no
    file_id / no token / not authorized / download fails / the file exceeds
    `max_bytes` (callers then fall back to uniform/demo segmentation).
    """
    import base64
    import os
    import tempfile
    from urllib.parse import quote

    context = context or {}
    token = context.get("access_token")
    if not file_id or not token:
        return None
    base = resolve_runtime_base_url(context).rstrip("/")
    # File names may contain spaces/brackets/# (Sinas `name` pattern is ^[^/]+$),
    # so percent-encode the path segment; the runtime decodes it server-side.
    url = f"{base}/files/{namespace}/{collection}/{quote(str(file_id), safe='')}"
    dest_dir = dest_dir or tempfile.gettempdir()
    name = os.path.basename(str(file_id))
    path = os.path.join(dest_dir, name if "." in name else name + ".mp4")
    try:
        import requests  # baseline dep

        resp = requests.get(
            url, headers={"Authorization": f"Bearer {token}"}, timeout=timeout
        )
        if resp.status_code != 200:
            return None
        b64 = (resp.json() or {}).get("content_base64")
        if not b64:
            return None
        # base64 is ~4/3 the raw size — reject oversize before decoding into RAM.
        if (len(b64) * 3) // 4 > max_bytes:
            return None
        raw = base64.b64decode(b64)
        if len(raw) > max_bytes:
            return None
        with open(path, "wb") as fh:
            fh.write(raw)
        return path
    except Exception:
        return None


class InMemoryStore:
    """Dict-backed stand-in for a Sinas state store. For tests/demo only."""

    def __init__(self) -> None:
        self._data: Dict[str, Dict[str, Any]] = {}

    def get(self, namespace_name: str, key: str) -> Optional[Any]:
        return self._data.get(namespace_name, {}).get(key)

    def set(self, namespace_name: str, key: str, value: Any) -> None:
        self._data.setdefault(namespace_name, {})[key] = value

    def all(self, namespace_name: str) -> Dict[str, Any]:
        return dict(self._data.get(namespace_name, {}))


class SinasStateClient:
    """Minimal Management/runtime state client over HTTP.

    Endpoints follow docs research (runtime /states). Kept tiny on purpose;
    swap for the official `sinas` SDK inside trusted functions.
    """

    def __init__(self, base_url: str, access_token: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.token = access_token
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def set_state(
        self, namespace: str, key: str, value: Any, visibility: str = "shared"
    ) -> dict:
        import requests  # lazy: requests is a baseline dep

        resp = requests.post(
            f"{self.base_url}/states",
            json={
                "namespace": namespace,
                "key": key,
                "value": value,
                "visibility": visibility,
            },
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_state(self, namespace: str, key: str) -> Optional[dict]:
        import requests

        resp = requests.get(
            f"{self.base_url}/states/{namespace}/{key}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
