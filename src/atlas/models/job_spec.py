"""Credential-free execution settings pinned by model job admission."""

import hashlib
import json
from pathlib import Path

from atlas.domain import StrictModel

from .contracts import BedrockConfig, Limits, PriceCard


class ModelJobSpec(StrictModel):
    model_id: str
    count_tokens_model_id: str | None = None
    region: str
    limits: Limits
    price_card: PriceCard

    def config(self):
        return BedrockConfig.model_validate(self.model_dump())

    def digest(self):
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def job_spec(config):
    return ModelJobSpec.model_validate(config.model_dump(exclude={"profile"}))


def load_job_spec(path):
    path = Path(path)
    if path.stat().st_size > 32768:
        raise ValueError("Model job spec exceeds budget")
    spec = ModelJobSpec.model_validate_json(path.read_bytes())
    spec.config().validate_live_price()
    return spec


def main():
    import argparse

    from atlas.artifacts import write_private_json

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    config = BedrockConfig.model_validate_json(Path(args.config).read_bytes())
    config.validate_live_price()
    output = Path(args.output).resolve()
    if not output.is_relative_to(Path("var").resolve()) or output.exists():
        parser.error("Choose a new spec file under private var/")
    spec = job_spec(config)
    write_private_json(output, spec.model_dump(mode="json"))
    print(json.dumps({"model_config_sha256": spec.digest(), "network_used": False}))


if __name__ == "__main__":
    main()
