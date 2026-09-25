"""Tests for the custom user model and soft delete aware user manager."""

import pytest

from apps.accounts.enums import UserRole
from apps.accounts.models import User

pytestmark = pytest.mark.django_db


class TestUserModel:
    """Behaviour of the custom user model."""

    def test_defaults_to_agent_role(self, agent):
        assert agent.role == UserRole.AGENT

    def test_email_is_unique(self, agent):
        from django.db import IntegrityError, transaction

        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="agent3", email=agent.email, password="TestPass123!")

    def test_soft_deleted_user_is_hidden_from_default_manager(self, agent):
        agent.soft_delete()

        assert not User.objects.filter(pk=agent.pk).exists()
        assert User.all_objects.filter(pk=agent.pk).exists()

    def test_soft_deleted_user_cannot_authenticate(self, agent):
        agent.soft_delete()

        assert agent.check_password("TestPass123!") is True
        assert not User.objects.filter(username=agent.username).exists()
