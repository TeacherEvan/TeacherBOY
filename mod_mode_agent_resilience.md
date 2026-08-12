# Fix: Make ModModeAgent resilient to None services

Update src/agents/mod_mode_agent.py:

1. Update __init__ type hints to Optional for services that can be None
2. Add guards in should_handle for mod_mode_service being None
3. Add guards in handle for each service usage, sending appropriate error messages when services are missing

Specifically:

In __init__:
- Change mod_mode_service: ModModeService -> mod_mode_service: ModModeService | None
- Similarly for ban_list_service, warning_service, harmful_detector, audit_log (though audit_log is already optional in main.py? Actually in main.py we pass mod_audit_log which can be None)
- dashboard_builder is always available (we create it in main.py)

In should_handle:
- When checking if mod mode is active, handle the case where self._mod_mode is None

In handle:
- Before using each service, check if it is None and if so, send an error message to the user indicating the service is not available, then return True (so the agent router knows we handled it, even if we couldn't perform the action).

We'll send a message like: "⚠️ Mod mode services are not available. Please check Convex configuration."

Let's implement the patch.