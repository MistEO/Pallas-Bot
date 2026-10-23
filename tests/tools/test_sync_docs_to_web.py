import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "scripts" / "sync_docs_to_web.py"


def load_sync_module():
    spec = importlib.util.spec_from_file_location("sync_docs_to_web", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_roundtrip_and_missing(tmp_path):
    mod = load_sync_module()
    assert mod.read_manifest(tmp_path) == []

    mod.write_manifest(tmp_path, {"src/b.md", "src/a.md"})
    assert mod.read_manifest(tmp_path) == ["src/a.md", "src/b.md"]


def test_read_manifest_ignores_corrupt_payload(tmp_path):
    mod = load_sync_module()
    (tmp_path / mod.SYNC_MANIFEST).write_text("{ not json", encoding="utf-8")
    assert mod.read_manifest(tmp_path) == []
    (tmp_path / mod.SYNC_MANIFEST).write_text('{"a": 1}', encoding="utf-8")
    assert mod.read_manifest(tmp_path) == []


def test_prune_stale_removes_only_unwritten_manifest_entries(tmp_path):
    mod = load_sync_module()
    kept = tmp_path / "src" / "plugins" / "duel.md"
    stale = tmp_path / "src" / "plugins" / "pb_protocol.md"
    kept.parent.mkdir(parents=True)
    kept.write_text("kept", encoding="utf-8")
    stale.write_text("stale", encoding="utf-8")

    removed = mod.prune_stale(
        tmp_path,
        {"src/plugins/duel.md"},
        ["src/plugins/duel.md", "src/plugins/pb_protocol.md", "src/plugins/gone.md"],
    )

    assert removed == ["src/plugins/pb_protocol.md"]
    assert kept.is_file()
    assert not stale.exists()
