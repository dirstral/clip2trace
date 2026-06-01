"""diagnose_runtime — probe runtime capabilities (libs, tools, disk, secrets).

Must be a sharedPool/trusted function for context["secrets"] to be present.
"""

from __future__ import annotations

import importlib
import shutil
import sys
import tempfile


def _has_module(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def handler(input_data, context):
    context = context or {}
    tmp = tempfile.gettempdir()
    try:
        free = shutil.disk_usage(tmp).free
    except Exception:
        free = None
    modules = ["av", "cv2", "scenedetect", "imagehash", "PIL", "numpy",
               "telethon", "rapidfuzz", "dateutil", "requests"]
    return {
        "python": sys.version.split()[0],
        "modules": {m: _has_module(m) for m in modules},
        "tools": {
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "tesseract": bool(shutil.which("tesseract")),
        },
        "tmp_dir": tmp,
        "tmp_free_bytes": free,
        "has_access_token": bool(context.get("access_token")),
        "secrets_available": "secrets" in context,
    }
