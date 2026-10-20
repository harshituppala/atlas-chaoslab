"""Lock installed dependency closures separately for core and optional ML."""

import tomllib
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def closure(roots):
    pending = [Requirement(value) for value in roots]
    visited = set()
    versions = {}
    while pending:
        request = pending.pop()
        name = canonicalize_name(request.name)
        key = (name, tuple(sorted(request.extras)))
        if key in visited:
            continue
        visited.add(key)
        installed = distribution(name)
        versions[name] = installed.version
        for raw in installed.requires or []:
            child = Requirement(raw)
            contexts = request.extras or {""}
            if child.marker is None or any(
                child.marker.evaluate({"extra": extra}) for extra in contexts
            ):
                pending.append(child)
    return versions


project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
core = closure(project["dependencies"] + project["optional-dependencies"]["test"])
embeddings = closure(project["optional-dependencies"]["embeddings"])
Path("requirements.lock").write_text(
    "# Core API, worker, and verification dependencies. No heavyweight embedding runtime.\n"
    + "\n".join(f"{name}=={version}" for name, version in sorted(core.items()))
    + "\n"
)
Path("requirements-embeddings.lock").write_text(
    "# Optional local model runtime; generated/validated on macOS arm64.\n-r requirements.lock\n"
    + "\n".join(
        f"{name}=={version}" for name, version in sorted(embeddings.items()) if name not in core
    )
    + "\n"
)
print(
    "Locked",
    len(core),
    "core packages and",
    len(set(embeddings) - set(core)),
    "optional embedding packages",
)
