"""Open Job cabinet and Spec-edit authorization."""
from job_cabinet import role_can_edit_unsupervised, role_can_request_override, role_can_open_blueprint_studio


def test_role_gates_are_minimal():
    assert role_can_edit_unsupervised("admin") is True
    assert role_can_edit_unsupervised("executive") is True
    assert role_can_edit_unsupervised("qc_supervisor") is False
    assert role_can_edit_unsupervised("qc_tech") is False
    assert role_can_request_override("qc_supervisor") is True
    assert role_can_request_override("qc_tech") is False
    assert role_can_request_override("admin") is False
    assert role_can_open_blueprint_studio("qc_tech") is False
    assert role_can_open_blueprint_studio("production") is False
    assert role_can_open_blueprint_studio("qc_supervisor") is True
    assert role_can_open_blueprint_studio("admin") is True
