from typing import Any
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.sell import Client, Sell


def test_create_client(
    test_client_authenticated_default: TestClient,
    db_session: Session,
):
    test_client = test_client_authenticated_default

    response = test_client.post(
        "/sells/client",
        json={
            "name": "Test Client",
            "description": "A client for testing purposes",
            "enterprise_code": "ENT123",
        },
    )
    assert response.status_code == status.HTTP_200_OK

    client_data = response.json().get("data")

    assert client_data is not None

    client_id = client_data.get("id")

    assert client_id is not None

    assert client_data.get("name") == "Test Client"
    assert client_data.get("description") == "A client for testing purposes"
    assert client_data.get("enterprise_code") == "ENT123"


def test_get_client(
    test_client_authenticated_default: TestClient,
    db_session: Session,
    create_default_user: dict[str, Any],
):
    test_client = test_client_authenticated_default

    client_id = create_default_user["clients"][0].id
    response = test_client.get(f"/sells/client/{client_id}")
    assert response.status_code == status.HTTP_200_OK

    client_data = response.json()["data"]
    assert client_data["id"] == client_id
    assert client_data["name"] == create_default_user["clients"][0].name
    assert client_data["description"] == create_default_user["clients"][0].description
    assert (
        client_data["enterprise_code"]
        == create_default_user["clients"][0].enterprise_code
    )
    assert client_data["person_code"] == create_default_user["clients"][0].person_code


def test_query_clients(
    test_client_authenticated_default: TestClient,
    create_default_user: dict[str, Any],
):
    test_client = test_client_authenticated_default

    response = test_client.get("/sells/client")
    assert response.status_code == status.HTTP_200_OK

    clients_data = response.json()["data"]
    assert len(clients_data) == len(create_default_user["clients"])

    for i, client_data in enumerate(clients_data):
        assert client_data["id"] == create_default_user["clients"][i].id
        assert client_data["name"] == create_default_user["clients"][i].name
        assert (
            client_data["description"] == create_default_user["clients"][i].description
        )
        assert (
            client_data["enterprise_code"]
            == create_default_user["clients"][i].enterprise_code
        )
        assert (
            client_data["person_code"] == create_default_user["clients"][i].person_code
        )


def test_delete_client(
    test_client_authenticated_default: TestClient,
    db_session: Session,
    create_default_user: dict[str, Any],
):
    test_client = test_client_authenticated_default

    client_id = create_default_user["clients"][0].id
    response = test_client.delete(f"/sells/client/{client_id}")
    assert response.status_code == status.HTTP_200_OK

    db_client = db_session.get(Client, client_id)
    assert db_client is None


def test_create_sell(
    test_client_authenticated_default: TestClient,
    db_session: Session,
    create_default_user: dict[str, Any],
):
    test_client = test_client_authenticated_default

    client_id = create_default_user["clients"][0].id
    product_id = create_default_user["products"][0].id
    user_id = create_default_user["user"].id

    response = test_client.post(
        "/sells/",
        json={
            "product_id": product_id,
            "client_id": client_id,
            "quantity": 2,
            "user_id": user_id,
        },
    )
    assert response.status_code == status.HTTP_200_OK

    sell_data = response.json()["data"]
    sell_id = sell_data["id"]

    db_sell = db_session.get(Sell, sell_id)
    assert db_sell is not None
    assert db_sell.product_id == product_id
    assert db_sell.client_id == client_id
    assert db_sell.quantity == 2


def test_create_my_sell(
    test_client_authenticated_default: TestClient,
    db_session: Session,
    create_default_user: dict[str, Any],
):
    test_client = test_client_authenticated_default

    product_id = create_default_user["products"][0].id
    user = create_default_user["user"]
    client_id = create_default_user["clients"][0].id

    print(f"User: {user}")

    response = test_client.post(
        "/sells/me",
        json={"client_id": client_id, "product_id": product_id, "quantity": 2},
    )
    assert response.status_code == status.HTTP_200_OK

    sell_data = response.json()["data"]
    product_id = sell_data["product_id"]
    user_id = sell_data["user_id"]

    with db_session:
        db_sell = list(
            filter(
                lambda k: k.quantity == 2,
                db_session.exec(
                    select(Sell).where(
                        Sell.product_id == product_id,
                        Sell.user_id == user_id,
                        Sell.client_id == client_id,
                    )
                ).all(),
            )
        )[0]

        assert db_sell is not None
        assert db_sell.product_id == product_id
        assert db_sell.user_id == user_id
        assert db_sell.quantity == 2


def test_get_my_sells(
    test_client_authenticated_default: TestClient,
    create_default_user: dict[str, Any],
):
    test_client = test_client_authenticated_default

    response = test_client.get("/sells/me")
    assert response.status_code == status.HTTP_200_OK

    sells_data = response.json()["data"]
    assert len(sells_data) == len(create_default_user["sells"])

    for i, sell_data in enumerate(sells_data):
        assert sell_data["user_id"] == create_default_user["sells"][i].user_id
        assert sell_data["product_id"] == create_default_user["sells"][i].product_id
        assert sell_data["quantity"] == create_default_user["sells"][i].quantity


def test_query_sells(
    test_client_authenticated_default: TestClient,
    create_default_user: dict[str, Any],
):
    test_client = test_client_authenticated_default

    user_id = create_default_user["sells"][0].user_id
    product_id = create_default_user["sells"][0].product_id
    client_id = create_default_user["sells"][0].client_id

    response = test_client.get(f"/sells/{user_id}/{client_id}/{product_id}")
    assert response.status_code == status.HTTP_200_OK

    sells_data = response.json()["data"]

    assert sells_data is not None
    assert type(sells_data) is dict

    assert sells_data["product_id"] == create_default_user["sells"][0].product_id
    assert sells_data["quantity"] == create_default_user["sells"][0].quantity


def test_read_sell(
    test_client_authenticated_default: TestClient,
    create_default_user: dict[str, Any],
):
    test_client = test_client_authenticated_default

    user_id = create_default_user["sells"][0].user_id
    product_id = create_default_user["sells"][0].product_id
    client_id = create_default_user["sells"][0].client_id

    response = test_client.get(f"/sells/{user_id}/{client_id}/{product_id}")
    assert response.status_code == status.HTTP_200_OK

    sell_data = response.json()["data"]
    assert sell_data["product_id"] == create_default_user["sells"][0].product_id
    assert sell_data["quantity"] == create_default_user["sells"][0].quantity


def test_delete_sell(
    test_client_authenticated_default: TestClient,
    db_session: Session,
    create_default_user: dict[str, Any],
):

    test_client = test_client_authenticated_default

    # sell_id = create_default_user["sells"][0].id

    product_id = create_default_user["products"][0].id
    user_id = create_default_user["user"].id
    client_id = create_default_user["clients"][0].id

    response = test_client.delete(f"/sells/{user_id}/{product_id}/{client_id}")
    assert response.status_code == status.HTTP_200_OK

    db_sell = db_session.exec(
        select(Sell)
        .where(Sell.product_id == product_id)
        .where(Sell.user_id == user_id)
        .where(Sell.client_id == client_id)
    ).first()

    assert db_sell is None
