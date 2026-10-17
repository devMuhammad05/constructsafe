from pathlib import Path

from constructsafe.config import load_config


def test_defaults_point_storage_under_data_dir():
    config = load_config()
    assert config.evidence_dir == config.data_dir / "evidence"
    assert config.database_path.parent == config.data_dir
    assert config.model_path == config.models_dir / config.model_weights


def test_env_overrides_are_typed(monkeypatch):
    monkeypatch.setenv("CONSTRUCTSAFE_CONFIDENCE_THRESHOLD", "0.6")
    monkeypatch.setenv("CONSTRUCTSAFE_FRAME_STRIDE", "4")
    monkeypatch.setenv("CONSTRUCTSAFE_DATA_DIR", "/tmp/cs")
    monkeypatch.setenv("CONSTRUCTSAFE_ALLOWED_VIDEO_EXTENSIONS", ".mp4, .avi")

    config = load_config()

    assert config.confidence_threshold == 0.6
    assert config.frame_stride == 4
    assert config.data_dir == Path("/tmp/cs")
    assert config.allowed_video_extensions == (".mp4", ".avi")


def test_explicit_overrides_win_over_env(monkeypatch):
    monkeypatch.setenv("CONSTRUCTSAFE_FRAME_STRIDE", "4")
    assert load_config(frame_stride=2).frame_stride == 2
