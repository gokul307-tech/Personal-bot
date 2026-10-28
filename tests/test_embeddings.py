import subprocess
import sys
from types import SimpleNamespace

from app.tools import embeddings


def test_importing_embedding_module_does_not_import_sentence_transformers():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import app.tools.embeddings; "
                "assert 'sentence_transformers' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_embedding_model_is_initialized_on_demand_and_cached(monkeypatch):
    instances = []

    class FakeSentenceTransformer:
        def __init__(self, model_name):
            self.model_name = model_name
            instances.append(self)

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    embeddings.get_embedding_model.cache_clear()

    try:
        first_model = embeddings.get_embedding_model()
        second_model = embeddings.get_embedding_model()

        assert first_model is second_model
        assert first_model.model_name == embeddings.EMBEDDING_MODEL
        assert len(instances) == 1
    finally:
        embeddings.get_embedding_model.cache_clear()
