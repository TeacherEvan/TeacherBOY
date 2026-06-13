# ModModeAgent Command Handlers Implementation Plan

> **For implementer:** Use TDD throughout. Write failing test first. Watch it fail. Then implement.

**Goal:** Implement actual functionality for `_handle_kick_command`, `_handle_warn_command`, `_handle_ban_command`, and `_handle_unban_command` in ModModeAgent to work without requiring the Flex dashboard.

**Architecture:** Direct command parsing from `/modmode kick @user`, `/modmode warn @user reason`, `/modmode ban @user reason`, `/modmode unban @user` with admin permission checks and integration with BanListService, WarningService, ModAuditLog, and LINE API kick.

**Tech Stack:** Python 3.11, pytest-asyncio, LINE Bot SDK v3, Convex backend, existing services (BanListService, WarningService, ModAuditLog)

---

### Task 1: Add test for `_handle_kick_command`

**Files:**
- Test: `tests/agents/test_mod_mode_agent.py` (extend existing)
- Modify: `src/agents/mod_mode_agent.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_handle_kick_command(agent, mock_services, event_factory):
    # Setup
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(True)
    mock_services["audit"].log_kick = _make_async_mock(None)
    event = event_factory("/modmode kick @U123", user_id="U456", group_id="C123")
    
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        with patch.object(agent, "_kick_user", new_callable=AsyncMock) as mock_kick:
            mock_kick.return_value = True
            result = await agent.handle(event, "/modmode kick @U123", MagicMock())
    
    assert result is True
    mock_kick.assert_called_once_with("C123", "U123", MagicMock(), "Kicked via /modmode kick")
    mock_services["audit"].log_kick.assert_called_once()

**Step 2: Run test — confirm it fails**
Command: `pytest tests/agents/test_mod_mode_agent.py::test_handle_kick_command -v`
Expected: FAIL — function not implemented

**Step 3: Write minimal implementation**

In `ModModeAgent._handle_kick_command`:
- Parse user ID from parts[2] (expect @user_id format)
- Verify admin permission
- Call `_kick_user(group_id, user_id, line_bot_api, reason)`
- Log audit with `log_kick`

**Step 4: Run test — confirm it passes**

**Step 5: Commit**

---

### Task 2: Add test for `_handle_warn_command`

**Files:**
- Test: `tests/agents/test_mod_mode_agent.py`
- Modify: `src/agents/mod_mode_agent.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_handle_warn_command(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(True)
    mock_services["warning"].warn_user = _make_async_mock({"count": 1, "should_ban": False, "reason": "Test reason"})
    mock_services["audit"].log_warn = _make_async_mock(None)
    event = event_factory("/modmode warn @U123 spam", user_id="U456", group_id="C123")
    
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        result = await agent.handle(event, "/modmode warn @U123 spam", MagicMock())
    
    assert result is True
    mock_services["warning"].warn_user.assert_called_once_with("C123", "U123", "U456", "spam")
    mock_services["audit"].log_warn.assert_called_once()

**Step 2: Run test — confirm it fails**

**Step 3: Write minimal implementation**

In `ModModeAgent._handle_warn_command`:
- Parse user ID from parts[2] and reason from parts[3:]
- Call `_warn_user(group_id, user_id, line_bot_api, reason)`
- Already handles auto-ban on 3rd warn via existing logic

**Step 4: Run test — confirm it passes**

**Step 5: Commit**

---

### Task 3: Add test for `_handle_ban_command`

**Files:**
- Test: `tests/agents/test_mod_mode_agent.py`
- Modify: `src/agents/mod_mode_agent.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_handle_ban_command(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(True)
    mock_services["ban_list"].ban_user = _make_async_mock({"groupId": "C123", "userId": "U123"})
    mock_services["audit"].log_ban = _make_async_mock(None)
    mock_services["audit"].log_kick = _make_async_mock(None)
    event = event_factory("/modmode ban @U123 repeated spam", user_id="U456", group_id="C123")
    
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        with patch.object(agent, "_kick_user", new_callable=AsyncMock) as mock_kick:
            mock_kick.return_value = True
            result = await agent.handle(event, "/modmode ban @U123 repeated spam", MagicMock())
    
    assert result is True
    mock_services["ban_list"].ban_user.assert_called_once_with("C123", "U123", "U456", "repeated spam")
    mock_kick.assert_called_once()
    mock_services["audit"].log_ban.assert_called_once()
    mock_services["audit"].log_kick.assert_called_once()

**Step 2: Run test — confirm it fails**

**Step 3: Write minimal implementation**

In `ModModeAgent._handle_ban_command`:
- Parse user ID and reason
- Call `ban_list_service.ban_user(group_id, user_id, admin_id, reason)`
- Call `_kick_user` immediately
- Log audit for both ban and kick

**Step 4: Run test — confirm it passes**

**Step 5: Commit**

---

### Task 4: Add test for `_handle_unban_command`

**Files:**
- Test: `tests/agents/test_mod_mode_agent.py`
- Modify: `src/agents/mod_mode_agent.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_handle_unban_command(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(True)
    mock_services["ban_list"].unban_user = _make_async_mock(True)
    mock_services["audit"].log_mode_change = _make_async_mock(None)
    event = event_factory("/modmode unban @U123", user_id="U456", group_id="C123")
    
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        result = await agent.handle(event, "/modmode unban @U123", MagicMock())
    
    assert result is True
    mock_services["ban_list"].unban_user.assert_called_once_with("C123", "U123")
    mock_services["audit"].log_mode_change.assert_called_once()

**Step 2: Run test — confirm it fails**

**Step 3: Write minimal implementation**

In `ModModeAgent._handle_unban_command`:
- Parse user ID from parts[2]
- Call `ban_list_service.unban_user(group_id, user_id)`
- Log audit (mode_change with unban action)

**Step 4: Run test — confirm it passes**

**Step 5: Commit**

---

### Task 5: Full verification

**Command:** `pytest tests/agents/test_mod_mode_agent.py -v`

**Expected:** All tests pass including new command handler tests

**Command:** `pytest tests/ -x -q`

**Expected:** All 837+ tests pass