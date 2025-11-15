import os
from pathlib import Path

from app import load_env_file


def test_load_env_file_ignores_comments_and_preserves_existing(tmp_path: Path, monkeypatch):
    env_path = tmp_path / ".env.test"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "OPENAI_API_KEY=abc123",
                "OPENAI_BASE_URL=https://example.com/v1",
                "RECIPE_IMAGE_MODEL=gpt-4o-mini",
            ]
        ),
        encoding="utf-8",
    )

    # Pre-set one variable to ensure load_env_file doesn't overwrite when override=False
    monkeypatch.setenv("OPENAI_API_KEY", "preset")

    # Ensure these are not pre-set from module import
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("RECIPE_IMAGE_MODEL", raising=False)
    loaded = load_env_file(str(env_path))
    assert loaded == 2  # BASE_URL + MODEL; API key preserved
    assert os.getenv("OPENAI_API_KEY") == "preset"
    assert os.getenv("OPENAI_BASE_URL") == "https://example.com/v1"
    assert os.getenv("RECIPE_IMAGE_MODEL") == "gpt-4o-mini"
