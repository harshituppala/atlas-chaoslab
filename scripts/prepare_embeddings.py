"""Download only a pinned public model snapshot; never execute repository code."""

import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(".cache/huggingface").resolve()))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
from huggingface_hub import snapshot_download

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
path = snapshot_download(
    repo_id=MODEL,
    revision=REVISION,
    token=False,
    local_dir=".cache/models/minilm",
    allow_patterns=[
        "config.json",
        "config_sentence_transformers.json",
        "sentence_bert_config.json",
        "modules.json",
        "1_Pooling/config.json",
        "model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "vocab.txt",
        "README.md",
    ],
)
print("Pinned embedding model available at", path)
