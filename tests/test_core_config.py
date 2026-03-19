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
