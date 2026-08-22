# Fix: Make ModModeAgent registration resilient to missing services

Instead of only registering ModModeAgent when all three services are available,
we should register it regardless and let it handle missing services gracefully.
This ensures the agent is available to process commands even when services
are temporarily unavailable or misconfigured.

Change in src/main.py around line 490-516:

FROM:
    # Register ModModeAgent (Priority: 4 - Intercepts messages in mod-enabled groups)
    # Must be registered before AdminAgent to intercept mod commands first
    global mod_mode_agent
    from src.services.mod_mode_service import get_mod_mode_service
    from src.services.ban_list_service import get_ban_list_service
    from src.services.warning_service import get_warning_service

    mod_mode_svc = get_mod_mode_service()
    ban_list_svc = get_ban_list_service()
    warning_svc = get_warning_service

    if mod_mode_svc and ban_list_svc and warning_svc:
        from src.agents.mod_mode_agent import ModModeAgent

        mod_dashboard = ModDashboardBuilder()
        mod_mode_agent = ModModeAgent(
            mod_mode_service=mod_mode_svc,
            ban_list_service=ban_list_svc,
            warning_service=warning_svc,
            harmful_detector=harmful_content_detector,
            audit_log=mod_audit_log,
            dashboard_builder=mod_dashboard,
        )
        agent_router.register_agent(mod_mode_agent)
        logger.info("🛡️ ModModeAgent registered (Priority 4 - group moderation)")
    else:
        logger.info("🛡️ ModModeAgent not registered (Convex not configured)")

TO:
    # Register ModModeAgent (Priority: 4 - Intercepts messages in mod-enabled groups)
    # Must be registered before AdminAgent to intercept mod commands first
    # Register regardless of service availability - agent will handle missing services gracefully
    global mod_mode_agent
    from src.agents.mod_mode_agent import ModModeAgent
    from src.services.mod_mode_service import get_mod_mode_service
    from src.services.ban_list_service import get_ban_list_service
    from src.services.warning_service import get_warning_service

    mod_mode_svc = get_mod_mode_service()
    ban_list_svc = get_ban_list_service()
    warning_svc = get_warning_service

    mod_dashboard = ModDashboardBuilder()
    mod_mode_agent = ModModeAgent(
        mod_mode_service=mod_mode_svc,
        ban_list_service=ban_list_svc,
        warning_service=warning_svc,
        harmful_detector=harmful_content_detector,
        audit_log=mod_audit_log,
        dashboard_builder=mod_dashboard,
    )
    agent_router.register_agent(mod_mode_agent)
    
    if mod_mode_svc and ban_list_svc and warning_svc:
        logger.info("🛡️ ModModeAgent registered (Priority 4 - group moderation)")
    else:
        logger.info("🛡️ ModModeAgent registered (Priority 4) but running in degraded mode - some features unavailable")