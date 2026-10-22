"""Provider resource-binding contract caught by real unauthenticated acceptance."""

from dataclasses import replace

import pytest
from test_login_exchange import CONFIG


@pytest.mark.parametrize(
    "scopes",
    [
        (),
        ("atlas/api",),
        ("openid",),
        ("https://another.invalid/api/review",),
        ("https://atlas.example.invalid/apix/review",),
        ("https://atlas.example.invalid/api/",),
    ],
)
def test_mismatched_or_absent_resource_scopes_fail_before_provider_setup(scopes):
    with pytest.raises(
        ValueError, match="Resource scopes must belong|requires explicit API scopes"
    ):
        replace(CONFIG, trust=replace(CONFIG.trust, required_scopes=scopes))


def test_bound_custom_scope_can_be_combined_with_oidc_scopes():
    config = replace(
        CONFIG,
        trust=replace(
            CONFIG.trust,
            required_scopes=("openid", "email", "https://atlas.example.invalid/api/review"),
        ),
    )
    assert config.trust.audience == "https://atlas.example.invalid/api"


def test_scope_prefix_does_not_silently_normalize_resource_identity():
    with pytest.raises(ValueError, match="Resource scopes must belong"):
        replace(CONFIG, trust=replace(CONFIG.trust, audience="https://atlas.example.invalid/api/"))
