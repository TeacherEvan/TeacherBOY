from unittest.mock import patch

from src.services.image_consent_service import ImageConsentService, image_consent_service


def test_admin_is_treated_as_consented_owner():
    service = ImageConsentService()

    with patch("src.services.image_consent_service.privilege_service") as mock_privilege:
        mock_privilege.is_admin.return_value = True

        assert service.is_consented_owner("U-admin") is True


def test_non_admin_is_not_treated_as_consented_owner():
    service = ImageConsentService()

    with patch("src.services.image_consent_service.privilege_service") as mock_privilege:
        mock_privilege.is_admin.return_value = False

        assert service.is_consented_owner("U-user") is False


def test_should_use_literal_mode_requires_declaration_and_consent():
    service = ImageConsentService()

    with patch("src.services.image_consent_service.privilege_service") as mock_privilege:
        mock_privilege.is_admin.return_value = True

        assert service.should_use_literal_mode("U-admin", declared_ai_generated=True) is True
        assert service.should_use_literal_mode("U-admin", declared_ai_generated=False) is False


def test_should_use_literal_mode_rejects_unconsented_users_even_when_declared():
    service = ImageConsentService()

    with patch("src.services.image_consent_service.privilege_service") as mock_privilege:
        mock_privilege.is_admin.return_value = False

        assert service.should_use_literal_mode("U-user", declared_ai_generated=True) is False
        assert service.should_use_literal_mode("U-user", declared_ai_generated=False) is False


def test_singleton_instance_is_available():
    assert isinstance(image_consent_service, ImageConsentService)
