from typing import Any, Generator
from unittest.mock import Mock, patch
import datetime
import json
from app.router.utils import (
    UserCreateEvent,
    UserDeleteEvent,
    UserDeleteWithId,
    UserUpdateEvent,
    UserUpdateWithId,
)
import pytest
from sqlalchemy.engine import Engine, create_engine
from sqlmodel import SQLModel, Session, StaticPool, select

from app.models.user import User, UserRead
from app.models.enterprise import Enterprise, EnterpriseRelation
from app.models.role import DefaultRole, Role, RoleRelation
from app.models.scope import DefaultScope, Scope, ScopeRelation
from app.messages.event import UpdateEvent


@pytest.fixture(scope="function")
def setup_db() -> Engine:
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    SQLModel.metadata.create_all(bind=engine)
    return engine


def gen_db(session: Session) -> Generator:
    yield session


def setup_db_defaults(local_db_session: Session) -> tuple[User, Enterprise]:
    enterprise = Enterprise(
        id=None, name="TestEnterprise", accountable_email="testenterprise@test.mail.com"
    )

    local_db_session.add(enterprise)
    local_db_session.commit()
    local_db_session.refresh(enterprise)

    assert enterprise.id is not None

    role = Role(
        id=None,
        name=DefaultRole.OWNER.value,
        description="Test Role Description",
        hierarchy=DefaultRole.get_default_hierarchy(DefaultRole.OWNER.value),
        enterprise_id=enterprise.id,
    )

    scope = Scope(
        id=None,
        name=DefaultScope.SELLS.value,
        description="Test Role Description",
        enterprise_id=enterprise.id,
    )

    scope_all = Scope(
        id=None,
        name=DefaultScope.ALL.value,
        description="Test Role Description",
        enterprise_id=enterprise.id,
    )

    enterprise.roles = [role]
    enterprise.scopes = [scope, scope_all]

    local_db_session.add(enterprise)
    local_db_session.commit()
    local_db_session.refresh(enterprise)

    saved_user = User(
        id=None,
        username="testuser",
        email="testemail@test.mail.com",
        full_name="Test User",
        role_id=enterprise.roles[0].id,
        scope_id=enterprise.scopes[0].id,
        enterprise_id=enterprise.id,
    )

    saved_user.role = enterprise.roles[0]
    saved_user.scope = enterprise.scopes[0]

    enterprise.users = [saved_user]

    local_db_session.add(enterprise)
    local_db_session.commit()
    local_db_session.refresh(saved_user)
    local_db_session.refresh(enterprise)

    return (saved_user, enterprise)


@pytest.mark.asyncio
@patch("app.messages.event.get_db")
async def test_create_user_event(mock_get: Mock, setup_db: Engine):
    connection = setup_db.connect()
    transaction = connection.begin()
    local_db_session = Session(autocommit=False, autoflush=False, bind=setup_db)

    with local_db_session:

        mock_get.return_value = gen_db(local_db_session)

        message_dict: dict[str, Any] = {
            **json.loads(
                UserCreateEvent(
                    event_scope=DefaultScope.SELLS.value,
                    data=UserRead(
                        id=5,
                        username="testuser2",
                        email="testemail2@test.mail.com",
                        full_name="Test User 2",
                        role=RoleRelation(
                            id=1, name=DefaultRole.OWNER.value, hierarchy=1
                        ),
                        scope=ScopeRelation(id=1, name=DefaultScope.ALL.value),
                        enterprise=EnterpriseRelation(
                            id=1,
                            name="TestEnterprise",
                            accountable_email="testenterprisemail@test.com",
                        ),
                        created_at=datetime.datetime.now(),
                    ),
                ).model_dump_json()
            ),
            "start_date": datetime.datetime.now().isoformat(),
            "origin": "rh_service",
        }

        # Arrange
        message = json.dumps(message_dict)

        # Act
        await UpdateEvent.process_message(message)

        mock_get.assert_called_once()

        # Assert
        user = local_db_session.exec(
            select(User).where(User.username == "testuser2")
        ).first()

        with local_db_session:
            assert user is not None
            assert user.username == "testuser2"
            assert user.email == "testemail2@test.mail.com"
            assert user.full_name == "Test User 2"
            assert user.role_id == message_dict["data"]["role"]["id"]
            assert user.scope_id == message_dict["data"]["scope"]["id"]
            assert user.enterprise_id == message_dict["data"]["enterprise"]["id"]

    transaction.rollback()

    if local_db_session.is_active:
        local_db_session.close()

    connection.close()


@pytest.mark.asyncio
@patch("app.messages.event.get_db")
async def test_update_user_event(mock_get: Mock, setup_db: Engine):
    connection = setup_db.connect()
    transaction = connection.begin()
    local_db_session = Session(autocommit=False, autoflush=False, bind=setup_db)

    mock_get.return_value = gen_db(local_db_session)

    saved_user, enterprise = setup_db_defaults(local_db_session)

    assert saved_user is not None
    assert enterprise is not None and enterprise.scopes is not None
    assert saved_user.id is not None
    assert saved_user.enterprise_id is not None
    assert saved_user.role is not None and saved_user.scope is not None
    assert saved_user.role.name is not None
    assert saved_user.role.hierarchy is not None
    assert saved_user.scope.name is not None
    assert saved_user.enterprise is not None
    assert saved_user.enterprise.name is not None

    # Arrange
    message_dict: dict[str, Any] = {
        **json.loads(
            UserUpdateEvent(
                event_scope=DefaultScope.SELLS.value,
                update_scope=DefaultScope.ALL.value,
                user=UserRead(
                    **saved_user.model_dump(),
                    role=RoleRelation(
                        id=saved_user.role.id,
                        name=saved_user.role.name,
                        hierarchy=saved_user.role.hierarchy,
                    ),
                    scope=ScopeRelation(
                        id=saved_user.scope.id,
                        name=saved_user.scope.name,
                    ),
                    enterprise=EnterpriseRelation(
                        id=saved_user.enterprise_id,
                        name=saved_user.enterprise.name,
                        accountable_email=enterprise.accountable_email,
                    )
                ),
                data=UserUpdateWithId(
                    id=saved_user.id,
                    enterprise_id=saved_user.enterprise_id,
                    username="updateduser",
                    email="updatedemail@test.mail.com",
                    scope_id=enterprise.scopes[1].id,
                ),
            ).model_dump_json()
        ),
        "start_date": datetime.datetime.now().isoformat(),
        "origin": "rh_service",
    }

    message = json.dumps(message_dict)

    local_db_session.close()

    # Act
    await UpdateEvent.process_message(message)

    mock_get.assert_called_once()

    # Assert
    new_session = Session(autocommit=False, autoflush=False, bind=setup_db)

    with new_session:
        user = new_session.exec(select(User).where(User.id == saved_user.id)).first()
        assert user is not None
        assert user.username == "updateduser"
        assert user.email == "updatedemail@test.mail.com"
        assert user.scope_id == message_dict["data"]["scope_id"]
        assert user.enterprise_id == message_dict["data"]["enterprise_id"]

    transaction.rollback()

    if new_session.is_active:
        new_session.close()

    if local_db_session.is_active:
        local_db_session.close()

    connection.close()


@pytest.mark.asyncio
@patch("app.messages.event.get_db")
async def test_delete_user_event(mock_get: Mock, setup_db: Engine):
    connection = setup_db.connect()
    transaction = connection.begin()
    local_db_session = Session(autocommit=False, autoflush=False, bind=setup_db)
    saved_user, _ = setup_db_defaults(local_db_session)

    assert saved_user is not None
    assert saved_user.id is not None

    mock_get.return_value = gen_db(local_db_session)

    assert saved_user.enterprise_id

    message_dict = {
        **json.loads(
            UserDeleteEvent(
                event_scope=DefaultScope.SELLS.value,
                data=UserDeleteWithId(
                    id=saved_user.id,
                    enterprise_id=saved_user.enterprise_id,
                ),
            ).model_dump_json()
        ),
        "start_date": datetime.datetime.now().isoformat(),
        "origin": "rh_service",
    }

    message = json.dumps(message_dict)

    local_db_session.close()

    # Act
    await UpdateEvent.process_message(message)

    mock_get.assert_called_once()

    # Assert
    new_session = Session(autocommit=False, autoflush=False, bind=setup_db)

    with new_session:
        user = new_session.get(User, saved_user.id)
        assert user is None

    transaction.rollback()

    if new_session.is_active:
        new_session.close()

    if local_db_session.is_active:
        local_db_session.close()

    connection.close()
