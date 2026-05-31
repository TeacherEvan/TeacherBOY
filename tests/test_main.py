"""Tests for main application."""

from contextlib import ExitStack
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("src.main.settings") as mock:
        mock.line_channel_secret = "test_secret"
        mock.line_channel_access_token = "test_token"
        mock.debug = False
        mock.is_convex_configured.return_value = False
        mock.is_convex_primary_backend.return_value = False
        mock.convex_deployment_url = None
        mock.convex_sync_token = None
        mock.convex_request_timeout_seconds = 10
        yield mock


@pytest.fixture
def client(mock_settings):
    """Create a test client."""
    from src.main import app

    return TestClient(app)


class _FakeRegisteredAgent:
    description = "test double"
    enabled = True

    def __init__(self, *args, **kwargs):
        self.name = self.__class__.__name__

    def get_priority(self):
        return 5


class _FakeHelpAgent(_FakeRegisteredAgent):
    pass


class _FakeReviewAgent(_FakeRegisteredAgent):
    pass


class _FakeSearchAgent(_FakeRegisteredAgent):
    pass


class _FakeLLMAgent(_FakeRegisteredAgent):
    pass


class _FakeSpecialNewsAgent(_FakeRegisteredAgent):
    pass


class _FakeNewsAgent(_FakeRegisteredAgent):
    pass


class _FakeConditionalAgent(_FakeRegisteredAgent):
    pass


class _FakeService:
    def __init__(self, *args, **kwargs):
        pass


class _FakeMessagingApi:
    def __init__(self, api_client):
        self.api_client = api_client

    def get_bot_info(self):
        return SimpleNamespace(user_id="U-test-bot")


class _FakeApiClient:
    def __init__(self, configuration):
        self.configuration = configuration

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _WebhookMessageEvent:
    def __init__(self, message, source):
        self.message = message
        self.source = source


class _WebhookTextMessageContent:
    def __init__(self, text, message_id="msg-1"):
        self.text = text
        self.id = message_id


class _WebhookMessagingApi:
    def __init__(self, api_client):
        self.api_client = api_client

    def get_profile(self, user_id):
        return SimpleNamespace(display_name="Alice")


def _fake_module(name: str, **attrs):
    module = ModuleType(name)
    for attr_name, value in attrs.items():
        setattr(module, attr_name, value)
    return module


@pytest.fixture
def readiness_lifespan_environment(mock_settings):
    """Patch startup-time dependencies while preserving the real app lifespan flow."""
    import src.main as main_module

    agent_router = main_module.agent_router
    app = main_module.app
    startup_loader = main_module.startup_loader

    agent_router.agents.clear()
    agent_router._priority_map.clear()
    agent_router._map_dirty = True
    original_bot_user_id = main_module.bot_user_id
    original_structured_records_service = main_module.structured_records_service

    original_loader_state = {
        "_calendar_required": startup_loader._calendar_required,
        "_staff_memory_required": startup_loader._staff_memory_required,
        "_memory_required": startup_loader._memory_required,
        "_documents_required": startup_loader._documents_required,
        "_logs_required": startup_loader._logs_required,
        "_calendar_loaded": startup_loader._calendar_loaded,
        "_staff_memory_loaded": startup_loader._staff_memory_loaded,
        "_memory_loaded": startup_loader._memory_loaded,
        "_documents_loaded": startup_loader._documents_loaded,
        "_logs_loaded": startup_loader._logs_loaded,
        "_backup_created": startup_loader._backup_created,
    }

    mock_settings.get_http_client_config.return_value = {
        "timeout": 5.0,
        "limits": {
            "max_connections": 10,
            "max_keepalive_connections": 5,
        },
        "http2": False,
    }
    mock_settings.bot_identity_storage_path = "./data/test_bot_identity.json"
    mock_settings.bot_identity_default_name = "Ms. Green"
    mock_settings.get_bot_identity_default_aliases.return_value = ["Ms. Green"]
    mock_settings.conversation_memory_enabled = False
    mock_settings.document_memory_enabled = False
    mock_settings.history_log_path = "./data/test_history"
    mock_settings.calendar_data_path = "./data/test_calendar"
    mock_settings.calendar_reminder_hour = 8
    mock_settings.calendar_sync_interval_seconds = 300
    mock_settings.news_api_key = None
    mock_settings.google_translate_api_key = None
    mock_settings.openrouter_default_model = "test-model"
    mock_settings.zeus_error_style = False
    mock_settings.admin_setup_key = None
    mock_settings.hf_memory_token = None
    mock_settings.hf_memory_repo_id = None
    mock_settings.document_hf_repo_id = None
    mock_settings.history_log_hf_repo_id = None
    mock_settings.history_log_encryption_key = None
    mock_settings.calendar_hf_repo_id = None
    mock_settings.is_google_translate_configured.return_value = False
    mock_settings.is_calendar_configured.return_value = False
    mock_settings.is_history_log_configured.return_value = False
    mock_settings.is_history_log_hf_configured.return_value = False
    mock_settings.is_calendar_hf_configured.return_value = False
    mock_settings.is_document_memory_configured.return_value = False
    mock_settings.is_github_models_configured.return_value = False
    mock_settings.is_profiler_configured.return_value = False
    mock_settings.is_brave_search_configured.return_value = False
    mock_settings.is_openrouter_configured.return_value = False
    mock_settings.is_news_api_configured.return_value = False
    mock_settings.is_convex_configured.return_value = False
    mock_settings.is_convex_primary_backend.return_value = False
    mock_settings.get_admin_user_ids.return_value = []

    fake_modules = {
        "src.agents.help_agent": _fake_module(
            "src.agents.help_agent", HelpAgent=_FakeHelpAgent
        ),
        "src.agents.admin_agent": _fake_module(
            "src.agents.admin_agent", AdminAgent=_FakeConditionalAgent
        ),
        "src.agents.calendar_agent": _fake_module(
            "src.agents.calendar_agent", CalendarAgent=_FakeConditionalAgent
        ),
        "src.agents.review_agent": _fake_module(
            "src.agents.review_agent", ReviewAgent=_FakeReviewAgent
        ),
        "src.agents.document_memory_agent": _fake_module(
            "src.agents.document_memory_agent",
            DocumentMemoryAgent=_FakeConditionalAgent,
        ),
        "src.agents.profiler_agent": _fake_module(
            "src.agents.profiler_agent", ProfilerAgent=_FakeConditionalAgent
        ),
        "src.agents.image_analyzer_agent": _fake_module(
            "src.agents.image_analyzer_agent", ImageAnalyzerAgent=_FakeConditionalAgent
        ),
        "src.agents.search_agent": _fake_module(
            "src.agents.search_agent", SearchAgent=_FakeSearchAgent
        ),
        "src.agents.llm_agent": _fake_module(
            "src.agents.llm_agent", LLMAgent=_FakeLLMAgent
        ),
        "src.agents.news_agent": _fake_module(
            "src.agents.news_agent", NewsAgent=_FakeNewsAgent
        ),
        "src.agents.special_news_agent": _fake_module(
            "src.agents.special_news_agent", SpecialNewsAgent=_FakeSpecialNewsAgent
        ),
        "src.services.news_data_service": _fake_module(
            "src.services.news_data_service", NewsDataService=_FakeService
        ),
        "src.services.special_news_service": _fake_module(
            "src.services.special_news_service", SpecialNewsService=_FakeService
        ),
        "src.services.staff_memory_service": _fake_module(
            "src.services.staff_memory_service", StaffMemoryService=_FakeService
        ),
    }

    with ExitStack() as stack:
        stack.enter_context(patch.dict("sys.modules", fake_modules))
        stack.enter_context(patch("src.main.ApiClient", _FakeApiClient))
        stack.enter_context(patch("src.main.MessagingApi", _FakeMessagingApi))
        stack.enter_context(patch("src.main.setup_tracing"))
        stack.enter_context(patch("src.main.openrouter_service.set_client"))
        stack.enter_context(patch("src.main.brave_search_service.set_client"))
        stack.enter_context(patch("src.main.github_models_service.set_client"))
        stack.enter_context(patch("src.main.configure_bot_identity_service"))
        stack.enter_context(patch("src.main.profiler_session_manager.start_cleanup"))
        stack.enter_context(patch("src.main.profiler_session_manager.stop_cleanup"))
        stack.enter_context(patch("src.main.news_session_manager.start_cleanup"))
        stack.enter_context(patch("src.main.news_session_manager.stop_cleanup"))
        stack.enter_context(
            patch("src.main.image_analyzer_session_manager.start_cleanup")
        )
        stack.enter_context(
            patch("src.main.image_analyzer_session_manager.stop_cleanup")
        )
        stack.enter_context(patch("src.main.calendar_session_manager.start_cleanup"))
        stack.enter_context(patch("src.main.calendar_session_manager.stop_cleanup"))
        stack.enter_context(patch("src.main.message_buffer_service.start_cleanup_task"))
        stack.enter_context(patch("src.main.message_buffer_service.stop_cleanup_task"))
        stack.enter_context(patch("src.main.rate_limiter.start_cleanup"))
        stack.enter_context(patch("src.main.rate_limiter.stop_cleanup"))
        stop_scheduler_mock = stack.enter_context(
            patch("src.main.reminder_service.stop_scheduler")
        )
        stack.enter_context(patch("src.main.calendar_service.stop"))
        stack.enter_context(patch("src.main.scheduler_service.stop"))
        yield (
            app,
            startup_loader,
            agent_router,
            stop_scheduler_mock,
            main_module.scheduler_service,
        )

    agent_router.agents.clear()
    agent_router._priority_map.clear()
    agent_router._map_dirty = True
    main_module.bot_user_id = original_bot_user_id
    main_module.structured_records_service = original_structured_records_service
    for attr_name, value in original_loader_state.items():
        setattr(startup_loader, attr_name, value)


def test_readiness_returns_503_after_degraded_lifespan_startup(
    readiness_lifespan_environment,
):
    """Readiness should stay degraded when startup finishes with required data still loading."""
    (
        app,
        startup_loader,
        _,
        stop_scheduler_mock,
        scheduler_service,
    ) = readiness_lifespan_environment

    async def degraded_ensure_data_loaded(*args, **kwargs):
        startup_loader._calendar_required = False
        startup_loader._calendar_loaded = False
        startup_loader._memory_required = True
        startup_loader._memory_loaded = False
        startup_loader._documents_required = False
        startup_loader._documents_loaded = False
        startup_loader._logs_required = False
        startup_loader._logs_loaded = False
        startup_loader._backup_created = False
        return {
            "calendar": True,
            "memory": False,
            "documents": True,
            "logs": True,
            "backup_created": False,
        }

    with patch(
        "src.main.startup_loader.ensure_data_loaded", degraded_ensure_data_loaded
    ):
        with TestClient(app) as client:
            response = client.get("/readiness")

    assert response.status_code == 503
    data = response.json()
    assert data["ready"] is False
    assert data["checks"]["startup_data"] == "loading"
    assert data["checks"]["agents_registered"] > 0
    stop_scheduler_mock.assert_called_once_with(scheduler_service)


def test_readiness_returns_200_after_healthy_lifespan_startup(
    readiness_lifespan_environment,
):
    """Readiness should report ready once the startup path marks required data loaded."""
    (
        app,
        startup_loader,
        _,
        stop_scheduler_mock,
        scheduler_service,
    ) = readiness_lifespan_environment

    async def healthy_ensure_data_loaded(*args, **kwargs):
        startup_loader._calendar_required = False
        startup_loader._calendar_loaded = False
        startup_loader._memory_required = True
        startup_loader._memory_loaded = True
        startup_loader._documents_required = False
        startup_loader._documents_loaded = False
        startup_loader._logs_required = False
        startup_loader._logs_loaded = False
        startup_loader._backup_created = True
        return {
            "calendar": True,
            "memory": True,
            "documents": True,
            "logs": True,
            "backup_created": True,
        }

    with patch(
        "src.main.startup_loader.ensure_data_loaded", healthy_ensure_data_loaded
    ):
        with TestClient(app) as client:
            response = client.get("/readiness")

    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["checks"]["startup_data"] == "ready"
    assert data["checks"]["agents_registered"] > 0
    stop_scheduler_mock.assert_called_once_with(scheduler_service)


def test_lifespan_does_not_initialize_structured_records_when_convex_is_not_primary(
    readiness_lifespan_environment,
    mock_settings,
):
    """Local-primary deployments should not initialize Convex structured records."""
    app, startup_loader, _, stop_scheduler_mock, scheduler_service = (
        readiness_lifespan_environment
    )
    mock_settings.is_convex_configured.return_value = True
    mock_settings.is_convex_primary_backend.return_value = False
    mock_settings.convex_deployment_url = "https://example.convex.cloud"
    convex_client_ctor = MagicMock()
    records_service_ctor = MagicMock()

    async def healthy_ensure_data_loaded(*args, **kwargs):
        startup_loader._calendar_required = False
        startup_loader._calendar_loaded = False
        startup_loader._memory_required = True
        startup_loader._memory_loaded = True
        startup_loader._documents_required = False
        startup_loader._documents_loaded = False
        startup_loader._logs_required = False
        startup_loader._logs_loaded = False
        startup_loader._backup_created = True
        return {
            "calendar": True,
            "memory": True,
            "documents": True,
            "logs": True,
            "backup_created": True,
        }

    with patch(
        "src.main.startup_loader.ensure_data_loaded", healthy_ensure_data_loaded
    ), patch("src.main.ConvexClient", convex_client_ctor), patch(
        "src.main.StructuredRecordsService", records_service_ctor
    ):
        with TestClient(app):
            pass

    convex_client_ctor.assert_not_called()
    records_service_ctor.assert_not_called()
    stop_scheduler_mock.assert_called_once_with(scheduler_service)


def test_lifespan_initializes_structured_records_when_convex_is_primary(
    readiness_lifespan_environment,
    mock_settings,
):
    """Convex-primary deployments should initialize structured records once."""
    app, startup_loader, _, stop_scheduler_mock, scheduler_service = (
        readiness_lifespan_environment
    )
    mock_settings.is_convex_configured.return_value = True
    mock_settings.is_convex_primary_backend.return_value = True
    mock_settings.convex_deployment_url = "https://example.convex.cloud"
    mock_settings.convex_sync_token = "sync-token"
    mock_settings.convex_request_timeout_seconds = 37

    shared_http_client = MagicMock(name="shared_http_client")
    shared_http_client.aclose = AsyncMock()
    convex_client = MagicMock(name="convex_client")
    records_service = MagicMock(name="structured_records_service")
    convex_client_ctor = MagicMock(return_value=convex_client)
    records_service_ctor = MagicMock(return_value=records_service)

    async def healthy_ensure_data_loaded(*args, **kwargs):
        startup_loader._calendar_required = False
        startup_loader._calendar_loaded = False
        startup_loader._memory_required = True
        startup_loader._memory_loaded = True
        startup_loader._documents_required = False
        startup_loader._documents_loaded = False
        startup_loader._logs_required = False
        startup_loader._logs_loaded = False
        startup_loader._backup_created = True
        return {
            "calendar": True,
            "memory": True,
            "documents": True,
            "logs": True,
            "backup_created": True,
        }

    with patch(
        "src.main.startup_loader.ensure_data_loaded", healthy_ensure_data_loaded
    ), patch(
        "src.main.create_optimized_http_client", return_value=shared_http_client
    ), patch("src.main.ConvexClient", convex_client_ctor), patch(
        "src.main.StructuredRecordsService", records_service_ctor
    ):
        with TestClient(app):
            pass

    convex_client_ctor.assert_called_once_with(
        base_url="https://example.convex.cloud",
        sync_token="sync-token",
        http_client=shared_http_client,
        timeout_seconds=37.0,
    )
    records_service_ctor.assert_called_once_with(convex_client=convex_client)
    shared_http_client.aclose.assert_awaited_once()
    stop_scheduler_mock.assert_called_once_with(scheduler_service)


def test_lifespan_wires_convex_calendar_and_staff_memory_when_convex_is_primary(
    readiness_lifespan_environment,
    mock_settings,
):
    """Convex-primary deployments should route calendar and staff memory through Convex."""
    app, _, _, stop_scheduler_mock, scheduler_service = readiness_lifespan_environment
    mock_settings.is_convex_configured.return_value = True
    mock_settings.is_convex_primary_backend.return_value = True
    mock_settings.convex_deployment_url = "https://example.convex.cloud"
    mock_settings.convex_sync_token = "sync-token"
    mock_settings.convex_request_timeout_seconds = 37
    mock_settings.is_calendar_configured.return_value = True
    mock_settings.is_calendar_hf_configured.return_value = True
    mock_settings.hf_memory_token = "hf-token"
    mock_settings.calendar_hf_repo_id = "teacherboy/calendar"

    shared_http_client = MagicMock(name="shared_http_client")
    shared_http_client.aclose = AsyncMock()
    convex_client = MagicMock(name="convex_client")
    calendar_repository = MagicMock(name="calendar_repository")
    staff_memory_repository = MagicMock(name="staff_memory_repository")
    structured_records_service = MagicMock(name="structured_records_service")
    staff_memory_service = MagicMock(name="staff_memory_service")

    ensure_data_loaded = AsyncMock(
        return_value={
            "calendar": True,
            "memory": True,
            "documents": True,
            "logs": True,
            "staff_memory": True,
            "backup_created": True,
        }
    )
    staff_memory_service_cls = MagicMock(return_value=staff_memory_service)

    with patch.dict(
        "sys.modules",
        {
            "src.services.staff_memory_service": _fake_module(
                "src.services.staff_memory_service",
                StaffMemoryService=staff_memory_service_cls,
            )
        },
    ), patch(
        "src.main.create_optimized_http_client", return_value=shared_http_client
    ), patch("src.main.ConvexClient", return_value=convex_client), patch(
        "src.main.StructuredRecordsService",
        return_value=structured_records_service,
    ), patch(
        "src.main.ConvexCalendarRepository", return_value=calendar_repository
    ) as calendar_repo_ctor, patch(
        "src.main.ConvexStaffMemoryRepository",
        return_value=staff_memory_repository,
    ) as staff_repo_ctor, patch(
        "src.main.calendar_service.configure"
    ) as calendar_configure, patch(
        "src.main.startup_loader.ensure_data_loaded", ensure_data_loaded
    ):
        with TestClient(app):
            pass

    calendar_repo_ctor.assert_called_once_with(convex_client)
    staff_repo_ctor.assert_called_once_with(convex_client)
    calendar_configure.assert_called_once_with(
        storage_path=mock_settings.calendar_data_path,
        hf_token=None,
        hf_repo_id=None,
        sync_interval_seconds=mock_settings.calendar_sync_interval_seconds,
        repository=calendar_repository,
    )
    staff_memory_service_cls.assert_called_once_with(
        Path("./data/staff_memory/staff_memory.json"),
        repository=staff_memory_repository,
    )
    ensure_call = ensure_data_loaded.await_args.kwargs
    assert ensure_call["calendar_service"] is not None
    assert ensure_call["staff_memory_service"] is staff_memory_service
    assert ensure_call["memory_service"] is None
    assert ensure_call["document_service"] is None
    assert ensure_call["history_log"] is None
    assert ensure_call["convex_client"] is convex_client
    assert ensure_call["calendar_backend"] == "convex"
    assert ensure_call["staff_memory_backend"] == "convex"
    shared_http_client.aclose.assert_awaited_once()
    stop_scheduler_mock.assert_called_once_with(scheduler_service)


def test_readiness_returns_503_when_convex_primary_healthcheck_fails(
    readiness_lifespan_environment,
    mock_settings,
):
    """Readiness should stay degraded when Convex-primary startup health checks fail."""
    app, _, _, stop_scheduler_mock, scheduler_service = readiness_lifespan_environment
    mock_settings.is_convex_configured.return_value = True
    mock_settings.is_convex_primary_backend.return_value = True
    mock_settings.convex_require_healthcheck_on_startup = True
    mock_settings.convex_deployment_url = "https://example.convex.cloud"
    mock_settings.convex_sync_token = "sync-token"
    mock_settings.is_calendar_configured.return_value = True

    shared_http_client = MagicMock(name="shared_http_client")
    shared_http_client.aclose = AsyncMock()
    convex_client = MagicMock(name="convex_client")
    convex_client.healthcheck = AsyncMock(return_value=False)

    class _RepositoryAwareStaffMemoryService:
        def __init__(self, storage_path, repository=None):
            self._storage_path = storage_path
            self._repository = repository

    with patch.dict(
        "sys.modules",
        {
            "src.services.staff_memory_service": _fake_module(
                "src.services.staff_memory_service",
                StaffMemoryService=_RepositoryAwareStaffMemoryService,
            )
        },
    ), patch(
        "src.main.create_optimized_http_client", return_value=shared_http_client
    ), patch("src.main.ConvexClient", return_value=convex_client), patch(
        "src.main.StructuredRecordsService", return_value=MagicMock()
    ), patch(
        "src.main.ConvexCalendarRepository", return_value=MagicMock()
    ), patch(
        "src.main.ConvexStaffMemoryRepository", return_value=MagicMock()
    ):
        with TestClient(app) as client:
            response = client.get("/readiness")

    assert response.status_code == 503
    assert response.json()["ready"] is False
    convex_client.healthcheck.assert_awaited()
    shared_http_client.aclose.assert_awaited_once()
    stop_scheduler_mock.assert_called_once_with(scheduler_service)


def test_lifespan_keeps_working_when_backend_is_local_and_convex_is_unset(
    readiness_lifespan_environment,
):
    """Local-primary startup should not depend on Convex being configured."""
    app, _, _, stop_scheduler_mock, scheduler_service = readiness_lifespan_environment
    convex_client_ctor = MagicMock()
    calendar_repo_ctor = MagicMock()
    staff_repo_ctor = MagicMock()

    with patch("src.main.ConvexClient", convex_client_ctor), patch(
        "src.main.ConvexCalendarRepository", calendar_repo_ctor
    ), patch("src.main.ConvexStaffMemoryRepository", staff_repo_ctor):
        with TestClient(app) as client:
            response = client.get("/readiness")

    assert response.status_code == 200
    convex_client_ctor.assert_not_called()
    calendar_repo_ctor.assert_not_called()
    staff_repo_ctor.assert_not_called()
    stop_scheduler_mock.assert_called_once_with(scheduler_service)


def test_lifespan_raises_when_convex_is_primary_but_not_configured(
    readiness_lifespan_environment,
    mock_settings,
):
    """Convex-primary startup should fail fast when Convex settings are missing."""
    app, _, _, _, _ = readiness_lifespan_environment
    mock_settings.is_convex_primary_backend.return_value = True
    mock_settings.is_convex_configured.return_value = False

    shared_http_client = MagicMock(name="shared_http_client")
    shared_http_client.aclose = AsyncMock()

    with patch(
        "src.main.create_optimized_http_client", return_value=shared_http_client
    ) as create_client:
        with pytest.raises(RuntimeError, match="Convex"):
            with TestClient(app):
                pass

    create_client.assert_not_called()
    shared_http_client.aclose.assert_not_awaited()


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"  # Updated from "ok"
    assert data["service"] == "Ms. Green Assistant"
    assert data["features"]["translation"] == "AI translation"
    assert data["features"]["translation_backend"] == "ai"
    assert "google_translate" not in data["features"]


def test_health_check(client):
    """Test health check endpoint."""
    with patch("src.main.startup_loader.is_ready", return_value=True), patch(
        "src.main.agent_router.list_agents",
        return_value=[{"name": "TranslationAgent", "enabled": True}],
    ):
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["checks"] == {
        "process": "alive",
        "startup_data": "ready",
        "agents_registered": 1,
    }


def test_health_check_does_not_call_translation_providers(client):
    """Health should remain a cheap liveness check without deep probes."""
    with patch("src.main.startup_loader.is_ready", return_value=False), patch(
        "src.main.agent_router.list_agents", return_value=[]
    ), patch(
        "src.main.github_models_service.chat_completion",
        side_effect=AssertionError("github models probe should not run"),
    ), patch(
        "src.main.openrouter_service.chat_completion",
        side_effect=AssertionError("openrouter probe should not run"),
    ):
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["checks"] == {
        "process": "alive",
        "startup_data": "loading",
        "agents_registered": 0,
    }


def test_readiness_returns_503_when_startup_is_not_ready(client):
    """Readiness should return 503 while startup prerequisites are still loading."""
    with patch("src.main.startup_loader.is_ready", return_value=False), patch(
        "src.main.agent_router.list_agents", return_value=[]
    ):
        response = client.get("/readiness")

    assert response.status_code == 503
    data = response.json()
    assert data["ready"] is False
    assert data["checks"]["startup_data"] == "loading"
    assert data["translation_backend"] == "ai"
    assert "google_translate_enabled" not in data


def test_readiness_returns_503_when_agents_exist_but_startup_is_still_loading(client):
    """Readiness should stay unavailable until startup data is fully loaded."""
    with patch("src.main.startup_loader.is_ready", return_value=False), patch(
        "src.main.agent_router.list_agents",
        return_value=[{"name": "TranslationAgent", "enabled": True}],
    ):
        response = client.get("/readiness")

    assert response.status_code == 503
    data = response.json()
    assert data["ready"] is False
    assert data["checks"]["startup_data"] == "loading"
    assert data["checks"]["agents_registered"] == 1


def test_readiness_returns_200_when_startup_and_agents_are_ready(client):
    """Readiness should return 200 once startup data is loaded and agents exist."""
    with patch("src.main.startup_loader.is_ready", return_value=True), patch(
        "src.main.agent_router.list_agents",
        return_value=[{"name": "TranslationAgent", "enabled": True}],
    ):
        response = client.get("/readiness")

    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["checks"]["startup_data"] == "ready"
    assert data["checks"]["agents_registered"] == 1
    assert data["translation_backend"] == "ai"
    assert "google_translate_enabled" not in data


def test_readiness_returns_503_when_startup_is_ready_but_no_agents_registered(client):
    """Readiness should stay unavailable until at least one agent is registered."""
    with patch("src.main.startup_loader.is_ready", return_value=True), patch(
        "src.main.agent_router.list_agents", return_value=[]
    ):
        response = client.get("/readiness")

    assert response.status_code == 503
    data = response.json()
    assert data["ready"] is False
    assert data["checks"]["startup_data"] == "ready"
    assert data["checks"]["agents_registered"] == 0


def test_webhook_invalid_signature(client):
    """Test webhook with invalid signature."""
    response = client.post(
        "/webhook",
        json={"events": []},
        headers={"X-Line-Signature": "invalid_signature"},
    )
    assert response.status_code == 400


def test_webhook_missing_signature(client):
    """Test webhook without signature header."""
    response = client.post("/webhook", json={"events": []})
    # Should return 400 for invalid signature
    assert response.status_code == 400


def test_webhook_unexpected_error_returns_generic_500(client):
    """Webhook should not leak internal exception details in 500 responses."""
    with patch("src.main.webhook_parser.parse", side_effect=ValueError("boom")):
        response = client.post(
            "/webhook",
            data="{}",
            headers={"X-Line-Signature": "sig"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "detail": "Internal server error",
    }


def test_webhook_request_body_failure_returns_generic_500(mock_settings):
    """Unexpected setup failures before parse should use the generic 500 response."""
    from src.main import app

    client = TestClient(app, raise_server_exceptions=False)

    with patch(
        "starlette.requests.Request.body",
        side_effect=RuntimeError("body read failed"),
    ):
        response = client.post(
            "/webhook",
            data="{}",
            headers={"X-Line-Signature": "sig"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "detail": "Internal server error",
    }


def test_webhook_upserts_user_and_records_inbound_interaction(client, mock_settings):
    """Webhook should mirror routed inbound messages into structured persistence."""
    from src.agents.agent_router import RouteResult

    event = _WebhookMessageEvent(
        message=_WebhookTextMessageContent("help", message_id="msg-123"),
        source=SimpleNamespace(
            type="user",
            user_id="U123",
            group_id=None,
            room_id=None,
        ),
    )
    records_service = MagicMock()
    records_service.upsert_user = AsyncMock()
    records_service.record_interaction = AsyncMock()
    route_message = AsyncMock(
        return_value=RouteResult(
            handled=True,
            agent_name="HelpAgent",
            message_type="text",
        )
    )

    with patch("src.main.MessageEvent", _WebhookMessageEvent), patch(
        "src.main.TextMessageContent", _WebhookTextMessageContent
    ), patch("src.main.ApiClient", _FakeApiClient), patch(
        "src.main.MessagingApi", _WebhookMessagingApi
    ), patch("src.main.webhook_parser.parse", return_value=[event]), patch(
        "src.main.agent_router.route_message", route_message
    ), patch("src.main.structured_records_service", records_service), patch(
        "src.main.bot_user_id", None
    ):
        response = client.post(
            "/webhook",
            data="{}",
            headers={"X-Line-Signature": "sig"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "success", "processed": 1}
    records_service.upsert_user.assert_awaited_once_with(
        line_user_id="U123",
        display_name="Alice",
        role=None,
    )
    records_service.record_interaction.assert_awaited_once_with(
        line_user_id="U123",
        source_chat_id="user_U123",
        message_type="text",
        direction="inbound",
        text_preview="help",
        handled_agent="HelpAgent",
    )


def test_webhook_structured_record_failures_are_non_fatal_for_local_backend(
    client, mock_settings
):
    """Local-primary deployments should ignore Convex mirror write failures."""
    event = _WebhookMessageEvent(
        message=_WebhookTextMessageContent("help", message_id="msg-123"),
        source=SimpleNamespace(
            type="user",
            user_id="U123",
            group_id=None,
            room_id=None,
        ),
    )
    records_service = MagicMock()
    records_service.upsert_user = AsyncMock(side_effect=RuntimeError("convex down"))
    records_service.record_interaction = AsyncMock(
        side_effect=RuntimeError("convex down")
    )
    route_message = AsyncMock(return_value=True)

    with patch("src.main.MessageEvent", _WebhookMessageEvent), patch(
        "src.main.TextMessageContent", _WebhookTextMessageContent
    ), patch("src.main.ApiClient", _FakeApiClient), patch(
        "src.main.MessagingApi", _WebhookMessagingApi
    ), patch("src.main.webhook_parser.parse", return_value=[event]), patch(
        "src.main.agent_router.route_message", route_message
    ), patch("src.main.structured_records_service", records_service), patch(
        "src.main.bot_user_id", None
    ):
        response = client.post(
            "/webhook",
            data="{}",
            headers={"X-Line-Signature": "sig"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "success", "processed": 1}
    route_message.assert_awaited_once()
    records_service.upsert_user.assert_awaited_once()
    records_service.record_interaction.assert_awaited_once_with(
        line_user_id="U123",
        source_chat_id="user_U123",
        message_type="text",
        direction="inbound",
        text_preview="help",
        handled_agent=None,
    )


def test_webhook_structured_record_failures_do_not_prevent_routing_for_convex_primary(
    client, mock_settings
):
    """Webhook routing should continue when Convex-backed structured writes fail."""
    from src.agents.agent_router import RouteResult

    mock_settings.is_convex_primary_backend.return_value = True
    event = _WebhookMessageEvent(
        message=_WebhookTextMessageContent("help", message_id="msg-123"),
        source=SimpleNamespace(
            type="user",
            user_id="U123",
            group_id=None,
            room_id=None,
        ),
    )
    records_service = MagicMock()
    records_service.upsert_user = AsyncMock(side_effect=RuntimeError("convex down"))
    records_service.record_interaction = AsyncMock(
        side_effect=RuntimeError("convex down")
    )
    route_message = AsyncMock(
        return_value=RouteResult(
            handled=True,
            agent_name="HelpAgent",
            message_type="text",
        )
    )

    with patch("src.main.MessageEvent", _WebhookMessageEvent), patch(
        "src.main.TextMessageContent", _WebhookTextMessageContent
    ), patch("src.main.ApiClient", _FakeApiClient), patch(
        "src.main.MessagingApi", _WebhookMessagingApi
    ), patch("src.main.webhook_parser.parse", return_value=[event]), patch(
        "src.main.agent_router.route_message", route_message
    ), patch("src.main.structured_records_service", records_service), patch(
        "src.main.bot_user_id", None
    ):
        response = client.post(
            "/webhook",
            data="{}",
            headers={"X-Line-Signature": "sig"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "success", "processed": 1}
    route_message.assert_awaited_once()
    records_service.upsert_user.assert_awaited_once()
    records_service.record_interaction.assert_awaited_once_with(
        line_user_id="U123",
        source_chat_id="user_U123",
        message_type="text",
        direction="inbound",
        text_preview="help",
        handled_agent="HelpAgent",
    )
