"""Unit tests for the user service layer."""

import pytest

from apps.accounts.enums import UserRole
from apps.accounts.models import User
from apps.accounts.services import UserService
from core.exceptions import NotFoundException

pytestmark = pytest.mark.django_db


class TestUserServiceCreate:
    """Tests for :meth:`UserService.create`."""

    def test_hashes_password_and_defaults_to_agent_role(self):
        user = UserService.create(
            username="newagent",
            email="newagent@example.com",
            password="S3cretPass!",
        )

        assert user.role == UserRole.AGENT
        assert user.check_password("S3cretPass!")
        assert user.password != "S3cretPass!"

    def test_stamps_audit_actor(self, admin_user):
        user = UserService.create(
            username="newagent",
            email="newagent@example.com",
            password="S3cretPass!",
            role=UserRole.AGENT,
            actor=admin_user,
        )

        assert user.created_by == admin_user
        assert user.updated_by == admin_user

    def test_accepts_extra_model_fields(self):
        user = UserService.create(
            username="newagent",
            email="newagent@example.com",
            password="S3cretPass!",
            role=UserRole.ADMIN,
            is_staff=True,
        )

        assert user.is_staff is True
        assert user.role == UserRole.ADMIN


class TestUserServiceGet:
    """Tests for :meth:`UserService.get`."""

    def test_returns_live_user(self, agent):
        assert UserService.get(agent.id) == agent

    def test_soft_deleted_user_raises_not_found(self, agent):
        agent.soft_delete()

        with pytest.raises(NotFoundException):
            UserService.get(agent.id)


class TestUserServiceIsAdmin:
    """Tests for :meth:`UserService.is_admin`."""

    def test_agent_is_not_admin(self, agent):
        assert UserService.is_admin(agent) is False

    def test_admin_role_counts(self):
        role_admin = User.objects.create_user(
            username="roleadmin",
            email="roleadmin@example.com",
            password="S3cretPass!",
            role=UserRole.ADMIN,
        )

        assert UserService.is_admin(role_admin) is True
        assert UserService.is_admin(object()) is False

    def test_staff_and_superuser_count(self, admin_user):
        assert UserService.is_admin(admin_user) is True
