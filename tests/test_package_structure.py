"""#5/#6 — offline structural guards for sinas-package.yaml.

Catches manifest/agent/component reference drift without a live instance.
Field-NAME correctness (camelCase inferred for collections/stores/components)
still requires `sinas validate`; see docs/research/sinas-investigation.md.
"""

import os

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "sinas-package.yaml")

# manifest resource `type` -> spec section key
TYPE_TO_SECTION = {
    "function": "functions", "agent": "agents", "skill": "skills",
    "collection": "collections", "store": "stores", "component": "components",
}
EXPECTED_COLLECTIONS = {"input-videos", "source-segments", "keyframes",
                        "telegram-media", "reports", "demo-fixtures"}
EXPECTED_STORES = {"jobs", "segments", "search-results", "candidate-matches",
                   "query-cache", "runtime-diagnostics"}


def _spec():
    with open(PKG) as f:
        return yaml.safe_load(f)["spec"]


def _declared(spec):
    return {t: {r["name"] for r in (spec.get(sec) or [])}
            for t, sec in TYPE_TO_SECTION.items()}


def _name(ref):
    """`clip2trace/foo` -> `foo`."""
    return str(ref).split("/", 1)[-1]


def test_expected_collections_and_stores_declared():
    decl = _declared(_spec())
    assert EXPECTED_COLLECTIONS <= decl["collection"]
    assert EXPECTED_STORES <= decl["store"]


def test_manifest_references_resolve_both_ways():
    spec = _spec()
    decl = _declared(spec)
    manifest = spec["manifests"][0]
    required = manifest["requiredResources"]

    # every manifest entry resolves to a declared resource of that type
    manifest_by_type = {t: set() for t in TYPE_TO_SECTION}
    for r in required:
        t = r["type"]
        assert t in TYPE_TO_SECTION, f"unknown manifest resource type: {t}"
        assert r["name"] in decl[t], f"manifest references missing {t}: {r['name']}"
        manifest_by_type[t].add(r["name"])

    # every declared resource appears in the manifest
    for t, names in decl.items():
        missing = names - manifest_by_type[t]
        assert not missing, f"declared {t}(s) absent from manifest: {missing}"


def test_agent_and_component_enabled_refs_resolve():
    spec = _spec()
    decl = _declared(spec)

    for agent in spec.get("agents") or []:
        for fn in agent.get("enabledFunctions") or []:
            assert _name(fn) in decl["function"], \
                f"{agent['name']} enables missing function {fn}"
        for sk in agent.get("enabledSkills") or []:
            ref = sk["skill"] if isinstance(sk, dict) else sk
            assert _name(ref) in decl["skill"], \
                f"{agent['name']} enables missing skill {ref}"
        for st in agent.get("enabledStores") or []:
            ref = st["store"] if isinstance(st, dict) else st
            assert _name(ref) in decl["store"], \
                f"{agent['name']} enables missing store {ref}"

    for comp in spec.get("components") or []:
        for fn in comp.get("enabledFunctions") or []:
            assert _name(fn) in decl["function"], \
                f"{comp['name']} enables missing function {fn}"
        for st in comp.get("enabledStores") or []:
            ref = st["store"] if isinstance(st, dict) else st
            assert _name(ref) in decl["store"], \
                f"{comp['name']} enables missing store {ref}"
