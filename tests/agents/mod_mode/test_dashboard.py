# tests/agents/mod_mode/test_dashboard.py
import pytest

from src.agents.mod_mode.dashboard import ModDashboardBuilder


@pytest.fixture
def builder():
    return ModDashboardBuilder()


def test_build_main_dashboard(builder):
    info = {"mode": "all", "activated_by": "U456", "is_active": True}
    flex = builder.build_main_dashboard("Group Name", "C123", info)
    assert flex["type"] == "bubble"
    assert "body" in flex
    assert "header" in flex


def test_build_ban_list_dashboard(builder):
    bans = [{"userId": "U1", "reason": "spam"}, {"userId": "U2", "reason": "harassment"}]
    flex = builder.build_ban_list_dashboard("C123", bans)
    assert flex["type"] == "bubble"


def test_build_kick_confirm(builder):
    flex = builder.build_kick_confirm("C123", "U999", "User Name")
    assert flex["type"] == "bubble"


def test_build_warn_confirm(builder):
    flex = builder.build_warn_confirm("C123", "U999", "User Name")
    assert flex["type"] == "bubble"


def test_build_settings_dashboard(builder):
    info = {"mode": "special", "activated_by": "U456", "special_user_id": "U789", "is_active": True}
    flex = builder.build_settings_dashboard("C123", info)
    assert flex["type"] == "bubble"
