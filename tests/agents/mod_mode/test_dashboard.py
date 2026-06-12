import pytest
from src.agents.mod_mode.dashboard import ModDashboardBuilder


@pytest.fixture
def builder():
    return ModDashboardBuilder()


def test_build_main_dashboard(builder):
    info = {"mode": "all", "activated_by": "U456", "is_active": True}
    flex = builder.build_main_dashboard("Group Name", "C123", info)
    assert flex["type"] == "bubble"
    assert "contents" in flex["body"]


def test_build_main_dashboard_special_mode(builder):
    info = {"mode": "special", "activated_by": "U456", "special_user_id": "U789", "is_active": True}
    flex = builder.build_main_dashboard("Group Name", "C123", info)
    assert flex["type"] == "bubble"
    body_contents = str(flex["body"]["contents"])
    assert "SPECIAL" in body_contents


def test_build_ban_list_dashboard(builder):
    bans = [{"userId": "U1", "reason": "spam"}, {"userId": "U2", "reason": "harassment"}]
    flex = builder.build_ban_list_dashboard("C123", bans)
    assert flex["type"] == "bubble"
    body_contents = str(flex["body"]["contents"])
    assert "BANNED USERS" in body_contents
    assert "U1" in body_contents
    assert "U2" in body_contents


def test_build_ban_list_dashboard_empty(builder):
    flex = builder.build_ban_list_dashboard("C123", [])
    assert flex["type"] == "bubble"
    body_contents = str(flex["body"]["contents"])
    assert "No banned users" in body_contents


def test_build_kick_confirm(builder):
    flex = builder.build_kick_confirm("C123", "U999", "User Name")
    assert flex["type"] == "bubble"
    body_contents = str(flex["body"]["contents"])
    assert "CONFIRM KICK" in body_contents
    assert "U999" in body_contents


def test_build_warn_confirm(builder):
    flex = builder.build_warn_confirm("C123", "U999", "User Name")
    assert flex["type"] == "bubble"
    body_contents = str(flex["body"]["contents"])
    assert "CONFIRM WARN" in body_contents


def test_build_settings_dashboard(builder):
    info = {"mode": "all"}
    flex = builder.build_settings_dashboard("C123", info)
    assert flex["type"] == "bubble"
    body_contents = str(flex["body"]["contents"])
    assert "MOD MODE SETTINGS" in body_contents
    assert "ALL" in body_contents