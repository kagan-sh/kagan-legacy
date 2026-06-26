from pathlib import Path

import pytest
import yaml

from kagan.core import Harness
from kagan.core.errors import ConfigurationError


def test_core_loads_config_from_repo_root(tmp_path: Path):
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text(
        yaml.safe_dump({"project_name": "demo", "base_branch": "develop"})
    )
    core = Harness(data_dir=tmp_path / "data", repo_root=tmp_path)
    assert core.config is not None
    assert core.config.project_name == "demo"
    assert core.config.base_branch == "develop"
    core.close()


def test_core_config_missing_raises(tmp_path: Path):
    # An explicit repo_root with no manifest must fail loudly, not boot configless.
    core = Harness(data_dir=tmp_path / "data", repo_root=tmp_path)
    with pytest.raises(ConfigurationError):
        _ = core.config
    core.close()


def test_core_without_repo_root_has_no_config(tmp_path: Path):
    # repo_root is None -> config is None, no crash, no cwd discovery.
    core = Harness(data_dir=tmp_path / "data")
    assert core.repo_root is None
    assert core.config is None
    core.close()
