from pathlib import Path

from core.config import load_settings
from retrieval.index import LocalEmbeddingIndex


def test_chroma_persist_path_is_portable_and_resolves_from_project() -> None:
    settings = load_settings()

    portable_path = LocalEmbeddingIndex._portable_persist_path(
        settings,
        settings.paths.chroma_dir,
    )

    assert portable_path == "data/chroma"
    assert LocalEmbeddingIndex._resolve_persist_path(settings, portable_path) == settings.paths.chroma_dir.resolve()


def test_absolute_manifest_path_remains_backward_compatible() -> None:
    settings = load_settings()
    absolute_path = Path(settings.paths.chroma_dir).resolve()

    assert LocalEmbeddingIndex._resolve_persist_path(settings, str(absolute_path)) == absolute_path
