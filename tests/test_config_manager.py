import pytest
from vf_core.config_manager import ConfigManager


def _cm(tmp_path, name="config.toml"):
    return ConfigManager(tmp_path / name)


def test_get_returns_default_for_missing_key(tmp_path):
    cm = _cm(tmp_path)
    assert cm.get("missing") is None
    assert cm.get("a.b.c", "default") == "default"


def test_set_and_get_nested(tmp_path):
    cm = _cm(tmp_path)
    cm.set("a.b.c", 123)
    assert cm.get("a.b.c") == 123
    assert cm.get("a.b") == {"c": 123}


def test_get_returns_deep_copy(tmp_path):
    cm = _cm(tmp_path)
    cm.set("section", {"key": [1, 2]})
    got = cm.get("section")
    got["key"].append(3)
    assert cm.get("section") == {"key": [1, 2]}  # internal state untouched


def test_set_deep_copies_value(tmp_path):
    cm = _cm(tmp_path)
    original = {"key": [1, 2]}
    cm.set("section", original)
    original["key"].append(3)
    assert cm.get("section") == {"key": [1, 2]}


def test_set_raises_on_non_dict_descent(tmp_path):
    cm = _cm(tmp_path)
    cm.set("a", 1)
    with pytest.raises(TypeError):
        cm.set("a.b", 2)


def test_has(tmp_path):
    cm = _cm(tmp_path)
    cm.set("a.b", 1)
    assert cm.has("a.b")
    assert cm.has("a")
    assert not cm.has("a.b.c")
    assert not cm.has("missing")


def test_load_missing_file_is_empty(tmp_path):
    cm = _cm(tmp_path, "does_not_exist.toml")
    cm.load()  # must not raise
    assert cm.get_all() == {}


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "config.toml"
    cm = ConfigManager(path)
    cm.set("plugins.sources", ["mock_message_source"])
    cm.set("SYSTEM.mapbox_api_key", "abc")
    cm.save()
    assert path.exists()

    reloaded = ConfigManager(path)
    reloaded.load()
    assert reloaded.get("plugins.sources") == ["mock_message_source"]
    assert reloaded.get("SYSTEM.mapbox_api_key") == "abc"


def test_save_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "dir" / "config.toml"
    cm = ConfigManager(path)
    cm.set("a", 1)
    cm.save()
    assert path.exists()


def test_load_invalid_toml_raises_value_error(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text("not = = valid toml")
    cm = ConfigManager(path)
    with pytest.raises(ValueError):
        cm.load()


def test_get_all_returns_copy(tmp_path):
    cm = _cm(tmp_path)
    cm.set("a", {"b": 1})
    snapshot = cm.get_all()
    snapshot["a"]["b"] = 999
    assert cm.get("a.b") == 1
