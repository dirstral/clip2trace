"""Guard: the dashboard component's deployable `sourceCode` stays in sync.

The package installs from `sinas-package.yaml`, so the component's `sourceCode`
block is the authoritative deployable copy — `components/dashboard.jsx` is the
readable dev copy. This asserts they match (so edits to one don't silently drift
from the other) and that the cautious provenance framing is present.
"""

import os
import re

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "sinas-package.yaml")
DEV_COPY = os.path.join(ROOT, "components", "dashboard.jsx")


def _dashboard_component():
    with open(PKG) as f:
        data = yaml.safe_load(f)
    comps = {c["name"]: c for c in data["spec"]["components"]}
    assert "dashboard" in comps, "no dashboard component in sinas-package.yaml"
    return comps["dashboard"]


def test_component_sourcecode_matches_dev_copy():
    comp = _dashboard_component()
    with open(DEV_COPY) as f:
        dev = f.read()
    assert comp["sourceCode"].strip() == dev.strip(), (
        "components/dashboard.jsx and the inline sourceCode block have drifted — "
        "re-embed the dev copy into sinas-package.yaml"
    )


def test_component_enabled_functions_exist():
    comp = _dashboard_component()
    with open(PKG) as f:
        data = yaml.safe_load(f)
    fn_names = {f"clip2trace/{fn['name']}" for fn in data["spec"]["functions"]}
    for ref in comp.get("enabledFunctions", []):
        assert ref in fn_names, f"component enables unknown function {ref}"


def test_component_keeps_cautious_provenance_framing():
    comp = _dashboard_component()
    src = comp["sourceCode"]
    # The UI must frame results as candidates, not proof.
    assert "likely Telegram source candidate" in src
    # No bare overclaim: any mention of "original" must be an explicit negation
    # (check a whitespace-normalized window so source line-wraps don't matter).
    normalized = re.sub(r"\s+", " ", src).lower()
    for m in re.finditer(r"original", normalized):
        window = normalized[max(0, m.start() - 60) : m.start()]
        assert (
            "never" in window or "not" in window
        ), f"overclaiming language near: ...{window}original..."
