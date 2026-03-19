import pytest
import core.config as core_config


@pytest.fixture(autouse=True)
def restore_data_dir(tmp_path):
    """Restore DATA_DIR/CONFIG_PATH/TAGS_PATH after each test."""
    orig_data_dir = core_config.DATA_DIR
    orig_config_path = core_config.CONFIG_PATH
    orig_tags_path = core_config.TAGS_PATH
    yield
    core_config.DATA_DIR = orig_data_dir
    core_config.CONFIG_PATH = orig_config_path
    core_config.TAGS_PATH = orig_tags_path


def test_set_data_dir_creates_directory(tmp_path):
    new_dir = tmp_path / "newdir"
    assert not new_dir.exists()
    core_config.set_data_dir(new_dir)
    assert new_dir.exists()


def test_set_data_dir_updates_paths(tmp_path):
    core_config.set_data_dir(tmp_path)
    assert core_config.CONFIG_PATH == str(tmp_path / "config.json")
    assert core_config.TAGS_PATH == str(tmp_path / "tags.json")


def test_set_data_dir_accepts_string(tmp_path):
    core_config.set_data_dir(str(tmp_path))
    assert core_config.CONFIG_PATH == str(tmp_path / "config.json")
    assert core_config.TAGS_PATH == str(tmp_path / "tags.json")


# --- record_tag / tag_in_collection ---

def test_record_tag_adds_to_empty_collection(tmp_path):
    core_config.set_data_dir(tmp_path)
    core_config.record_tag("apple:123", {"name": "Test", "type": "album"})
    tags = core_config._load_tags()
    assert len(tags) == 1
    assert tags[0]["tag_string"] == "apple:123"


def test_record_tag_deduplicates(tmp_path):
    core_config.set_data_dir(tmp_path)
    core_config.record_tag("apple:123", {"name": "First"})
    core_config.record_tag("apple:123", {"name": "Second"})
    tags = core_config._load_tags()
    assert len(tags) == 1
    assert tags[0]["name"] == "Second"


def test_record_tag_prepends(tmp_path):
    core_config.set_data_dir(tmp_path)
    core_config.record_tag("apple:111", {"name": "First"})
    core_config.record_tag("apple:222", {"name": "Second"})
    tags = core_config._load_tags()
    assert tags[0]["tag_string"] == "apple:222"
    assert tags[1]["tag_string"] == "apple:111"


def test_record_tag_adds_written_at(tmp_path):
    from datetime import datetime
    core_config.set_data_dir(tmp_path)
    core_config.record_tag("apple:123", {})
    tags = core_config._load_tags()
    written_at = tags[0]["written_at"]
    datetime.fromisoformat(written_at)  # raises if not valid ISO 8601


def test_tag_in_collection_true(tmp_path):
    core_config.set_data_dir(tmp_path)
    core_config.record_tag("apple:123", {})
    assert core_config.tag_in_collection("apple:123") is True


def test_tag_in_collection_false(tmp_path):
    core_config.set_data_dir(tmp_path)
    assert core_config.tag_in_collection("apple:999") is False
