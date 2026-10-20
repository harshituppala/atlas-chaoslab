import pytest

from atlas.lab_container import configuration


def test_container_refuses_implicit_network_listener():
    with pytest.raises(ValueError, match="opt-in"):
        configuration({"ATLAS_LAB_ORIGIN": "https://lab.example.test"})


def test_container_requires_explicit_external_origin():
    with pytest.raises(ValueError, match="exact external origin"):
        configuration({"ATLAS_LAB_CONTAINER": "1"})


@pytest.mark.parametrize("port", ["0", "65536", "oops", "-1"])
def test_invalid_container_port_is_rejected_before_binding(port):
    with pytest.raises(ValueError, match="port"):
        configuration(
            {
                "ATLAS_LAB_CONTAINER": "1",
                "ATLAS_LAB_ORIGIN": "https://lab.example.test",
                "PORT": port,
            }
        )


def test_container_configuration_preserves_explicit_origin_and_valid_port():
    assert configuration(
        {"ATLAS_LAB_CONTAINER": "1", "ATLAS_LAB_ORIGIN": "https://lab.example.test", "PORT": "9000"}
    ) == ("https://lab.example.test", 9000)
