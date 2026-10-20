from hashlib import sha256

import pytest
from sqlalchemy import create_engine

from atlas.domain import Document
from atlas.pg_retrieval import PersistentHybridIndex, corpus_identity


def test_persistent_cache_key_binds_sources_and_recipe_not_input_order():
    documents = [
        Document(id="a", title="A", text="AES encryption.", kind="knowledge"),
        Document(id="b", title="B", text="SAML SSO.", kind="knowledge"),
    ]
    recipe = sha256(b"authored synthetic recipe").hexdigest()
    assert corpus_identity(documents, recipe) == corpus_identity(list(reversed(documents)), recipe)
    changed = [documents[0].model_copy(update={"text": "Different encryption."}), documents[1]]
    assert corpus_identity(documents, recipe)[0] != corpus_identity(changed, recipe)[0]
    assert (
        corpus_identity(documents, recipe)[0]
        != corpus_identity(documents, sha256(b"new recipe").hexdigest())[0]
    )


def test_persistent_search_never_silently_falls_back_to_sqlite():
    with pytest.raises(ValueError, match="PostgreSQL"):
        PersistentHybridIndex(create_engine("sqlite://"), "a", [], object())
