import asyncio
from collections.abc import Callable
import datetime
import json
from sys import stdout
from typing import Any

from app.db.conn import get_db
from app.models.enterprise import Enterprise
from app.models.role import BaseRole, Role
from app.models.scope import BaseScope, DefaultScope, Scope
from app.models.user import User, UserRead
from app.router.utils import EnterpriseEvents, UserEvents
from sqlmodel import Session


class UpdateEvent:
    def __init__(
        self,
        event: str,
        event_scope: str,
        data: dict[str, Any],
        start_date: datetime.datetime,
        origin: str,
        update_scope: str | None = None,
        full_user: dict[str, Any] | None = None,
    ):
        #pylint: disable=too-many-arguments

        self.event = event
        self.event_scope = event_scope
        self.data = data
        self.start_date = start_date
        self.origin = origin
        self.update_scope = update_scope
        self.full_user = full_user

    @classmethod
    def create_from_message(cls, message: str) -> "UpdateEvent | None":
        message_dict = {}
        try:
            message_dict = json.loads(message)
        except json.JSONDecodeError:
            print("Error: Failed to decode message")
            print("Invalid Message: ", message)
            return None

        if any(
            map(
                lambda x: x not in message_dict,
                ("event", "event_scope", "data", "origin", "start_date"),
            )
        ):
            print("Error: RECEIVED INVALID MESSAGE")
            print("Invalid Message: ", message)
            return None

        return cls(
            message_dict["event"],
            message_dict["event_scope"],
            message_dict["data"],
            datetime.datetime.fromisoformat(message_dict["start_date"]),
            message_dict["origin"],
            update_scope=message_dict.get("update_scope", None),
            full_user=message_dict.get("user", None),
        )

    @classmethod
    async def process_message(cls, message: str):
        print("Creating message processor...")
        print(f"Received message: {message}")
        event = cls.create_from_message(message)
        if event is not None:
            print("Updating table")
            await event.update_table()
        else:
            print("Event is Invalid")

        stdout.flush()

    def _check_valid_user_event(self):
        user_events = (
            UserEvents.USER_CREATED,
            UserEvents.USER_UPDATED,
            UserEvents.USER_DELETED,
        )
        enterprise_events = (
            EnterpriseEvents.ENTERPRISE_CREATED,
            EnterpriseEvents.ENTERPRISE_UPDATED,
            EnterpriseEvents.ENTERPRISE_DELETED,
        )

        if self.event in (user_events + enterprise_events):
            check_update_scope = ""
            check_update_scope = (
                self.update_scope if self.update_scope is not None else ""
            )
            print(
                f"""Checking valid event scope:
                {any((
                    self.event_scope == DefaultScope.SELLS.value,
                    check_update_scope == DefaultScope.SELLS.value,
                    ))}
                """
            )
            return any(
                (
                    self.event_scope == DefaultScope.SELLS.value,
                    # self.event_scope == DefaultScope.ALL.value,
                    check_update_scope == DefaultScope.SELLS.value,
                    # check_update_scope == DefaultScope.ALL.value
                )
            )

        print("Ignoring event for SELLERS.")
        return False

    async def __db_access_loop(self, db_function_callback: Callable, retries: int=5):
        #pylint: disable=broad-exception-caught,broad-exception-raised

        db: Session | None = None
        err: Exception | None = None
        counter = retries
        print(f"Start update: Data -- {self.data}")
        while counter > 0:
            try:
                db = next(get_db())
                if db is None:
                    print("No database connection")
                    print("Waiting for 5 seconds...")
                    await asyncio.sleep(5)
                    counter -= 1
                    continue

                db_function_callback(db)

                if db.is_active:
                    db.close()

                break

            except Exception as db_ex:
                print("Messaging error: ", str(db_ex))
                err = db_ex
                if db:
                    db.rollback()
                    if db.is_active:
                        db.close()
                    await asyncio.sleep(5)
                    counter -= 1
                    continue

        if counter == 0:
            print("Failed to update the database")
            print("Data: ", self.data)
            if db is None:
                print("No database connection")
                stdout.flush()
                raise Exception("Failed to connect to the database")
            if err:
                print(f"Error {str(err)}: ", err)
                stdout.flush()
                raise err

    async def update_table(self):
        if not self._check_valid_user_event():
            return

        if self.event == UserEvents.USER_CREATED:
            print("Received CreateUser event")
            await self.create_user()
        elif self.event == UserEvents.USER_DELETED:
            print("Received DeleteUser event")
            await self.delete_user()
        elif self.event == UserEvents.USER_UPDATED:
            print("Received UpdateUser event")
            await self.update_user()

        stdout.flush()

    async def update_user(self):
        #pylint: disable=broad-exception-caught,too-many-branches,too-many-statements

        def db_access(db: Session):
            #pylint: disable=too-many-branches,too-many-statements

            name = ""
            user_id = 0

            try:
                role: Role | None = None
                scope: Scope | None = None

                print(f"Start User update: Data -- {self.data}")

                if (
                    self.full_user is not None
                    and self.data.get("enterprise_id")
                    and self.data.get("id")
                ):

                    with db as session:
                        print("Interacting with the database...")

                        user_read = UserRead(**self.full_user)
                        db_user = session.get(User, self.data["id"])

                        if db_user is not None:
                            name = db_user.username
                            user_id = db_user.id

                            print(f"Found User {name} - ID {user_id}")

                            if user_read.scope.name not in (
                                DefaultScope.ALL.value,
                                DefaultScope.SELLS.value
                            ):

                                print(
                                    f"Deleting User: {user_read.username} -- ID {user_read.id}"
                                )
                                session.delete(db_user)
                                session.commit()
                                return

                            if self.data["role_id"]:
                                role = session.get(Role, self.data["role_id"])
                            elif "role_name" in self.data:
                                role = session.exec(
                                    BaseRole.get_roles_by_names(
                                        self.data["enterprise_id"],
                                        [self.data["role_name"]],
                                    )
                                ).first()

                                if "scope_id" in self.data:
                                    scope = session.get(Scope, self.data["scope_id"])
                                elif "scope_name" in self.data:
                                    scope = session.exec(
                                        BaseScope.get_roles_by_names(
                                            self.data["enterprise_id"],
                                            [self.data["scope_name"]],
                                        )
                                    ).first()

                                print("finding user...")

                            if role is not None:
                                print("Change role")
                                db_user.role_id = role.id
                                db_user.role = role

                            if scope is not None:
                                print("Change scope")
                                db_user.scope_id = scope.id
                                db_user.scope = scope

                            if "username" in self.data:
                                print("Updating Username")
                                db_user.username = self.data["username"]

                            if "email" in self.data:
                                print("Updating email")
                                db_user.email = self.data["email"]

                            if "full_name" in self.data:
                                print("Updating full_name")
                                db_user.full_name = self.data["full_name"]

                            print("Updating user on DB...")

                            session.add(db_user)
                            session.commit()

                            ################## VERIFYING SAVED USER ############
                            user_v = session.get(User, self.data["id"])
                            assert user_v is not None
                            print(f"User updated: {user_v.model_dump()}")

                        else:
                            print(f'User with id {self.data["id"]} not found')

                            if user_read.scope.name in (
                                DefaultScope.ALL.value,
                                DefaultScope.SELLS.value
                            ):
                                session.add(User(**user_read.model_dump()))
                                session.commit()

            except Exception as db_ex:
                print(f"Failed to update user {name} - ID: {user_id} on DB")
                print(f"Error: {db_ex}")

        await self.__db_access_loop(db_access)

    async def create_user(self):
        def db_access(db: Session):
            #pylint: disable=broad-exception-caught
            try:
                print(f"Start User creation: Data -- {self.data}")
                read_data = self.data.copy()
                role = Role(**read_data.pop("role"))
                scope = Scope(**read_data.pop("scope"))
                enterprise = Enterprise(**read_data.pop("enterprise"))
                date_created = read_data.get("created_at", None)

                with db as session:
                    user = User(**read_data)
                    user.role_id = role.id
                    user.scope_id = scope.id
                    user.enterprise_id = enterprise.id
                    user.created_at = (
                        datetime.datetime.fromisoformat(date_created)
                        if date_created is not None
                        else datetime.datetime.now()
                    )
                    session.add(user)

                    session.commit()

            except Exception as db_ex:
                print("Failed to create user")
                print(f"Error: {db_ex}")

        await self.__db_access_loop(db_access)

    async def delete_user(self):
        def db_access(db: Session):
            print(f"Start User deletion: Data -- {self.data}")
            with db as session:
                user = session.get(User, self.data["id"])
                if user is not None:
                    print("Deleting user...")
                    session.delete(user)
                    session.commit()
                else:
                    print(f'User with id {self.data["id"]} not found')

        await self.__db_access_loop(db_access)

    # async def create_enterprise(self):
    #     def db_access(db: Session):
    #         with db as session:
    #             enterprise = EnterpriseWithHierarchy(**self.data)
    #             enterprise_table= Enterprise(
    #                 name=enterprise.name,
    #                 id=enterprise.id,
    #                 users=enterprise.users,
    #                 scopes=list(
    #                     map(lambda e: Scope(**e.model_dump()), enterprise.scopes)
    #                 ) if enterprise.scopes else [],
    #                 roles=list(
    #                     map(lambda r: Role(**r.model_dump()), enterprise.roles)
    #                 ) if enterprise.roles else [],
    #                 accountable_email=enterprise.accountable_email,
    #                 activity_type=enterprise.activity_type,
    #             )
    #             print("Creating enterprise...")
    #             session.add(enterprise_table)
    #             session.commit()
    #
    #     await self.__db_access_loop(db_access)

    # async def update_enterprise(self):
    #     def db_access(db: Session):
    #         print(f"Start Enterprise update: Data -- {self.data}")

    #         if self.data.get("id"):
    #             with db as session:
    #                 print("Interacting with the database...")

    #                 enterprise = session.get(Enterprise, self.data["id"])

    #                 if enterprise:
    #                     if "name" in self.data:
    #                         enterprise.name = self.data["name"]

    #                     if "accountable_email" in self.data:
    #                         enterprise.accountable_email = self.data["accountable_email"]

    #                     if "activity_type" in self.data:
    #                         enterprise.activity_type = self.data["activity_type"]

    #                     print("Updating enterprise...")
    #                     session.add(enterprise)
    #                     session.commit()

    #                 else:
    #                     print(f'Enterprise with id {self.data["id"]} not found')

    #     await self.__db_access_loop(db_access)

    # async def delete_enterprise(self):
    #     def db_access(db: Session):
    #         print(f"Start Enterprise deletion: Data -- {self.data}")

    #         if self.data.get("id"):
    #             with db as session:
    #                 enterprise = session.get(Enterprise, self.data["id"])

    #                 if enterprise is not None:
    #                     print("Deleting enterprise...")
    #                     session.delete(enterprise)
    #                     session.commit()

    #                 else:
    #                     print(f'Enterprise with id {self.data["id"]} not found')

    #     await self.__db_access_loop(db_access)
