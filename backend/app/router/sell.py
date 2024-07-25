from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, and_, col, select
from app.db.conn import get_db
from app.middlewares.auth import authenticate_user, authorize_user
from app.models.role import DefaultRole
from app.models.scope import DefaultScope
from app.models.sell import BaseProduct, BaseSell, Client, ClientCreate, ClientRead, ClientResponse, Sell, SellCreate, SellCreateMe, SellDetailResponse, SellsResponse, UserSells, UserSellsListResponse
from app.models.user import User, UserRead


router = APIRouter(prefix="/sells")


class DefaultResponse(BaseModel):
    status: str = "OK"
    message: str = "Operation successful"


class ClientReadList(BaseModel):
    data: list[ClientRead]


@router.post("/client", response_model=ClientResponse)
def create_client(
    client: ClientCreate,
    db_session: Session = Depends(get_db),
    current_user: UserRead = Depends(authenticate_user),
) -> ClientResponse:
    authorize_user(
        user=current_user,
        operation_scopes=[
            DefaultScope.ALL.value, 
            DefaultScope.SELLS.value],
        operation_hierarchy_order=DefaultRole.get_default_hierarchy(
            DefaultRole.COLLABORATOR)
    )

    if current_user.enterprise_id is None:
        raise HTTPException(status_code=400, detail="User has no enterprise")

    with db_session:
        db_client = Client(**client.model_dump(), enterprise_id=current_user.enterprise_id)
        db_session.add(db_client)
        db_session.commit()
        db_session.refresh(db_client)

        return ClientResponse(data=ClientRead(**db_client.model_dump()))


@router.get("/client/{client_id}", response_model=ClientResponse)
def get_client(
    client_id: int,
    db_session: Session = Depends(get_db),
    current_user: UserRead = Depends(authenticate_user),
) -> ClientResponse:

    with db_session:
        db_client = db_session.exec(
            select(Client)
                .where(col(Client.id) == client_id)
                .where(col(Client.enterprise_id) == current_user.enterprise_id)
        ).first()

        if db_client is None:
            raise HTTPException(status_code=404, detail="Client not found")

        authorize_user(
            user=current_user,
            operation_scopes=[
                DefaultScope.ALL.value, 
                DefaultScope.SELLS.value],
            operation_hierarchy_order=DefaultRole.get_default_hierarchy(
                DefaultRole.COLLABORATOR
            ),
            custom_checks=(
                current_user.role.hierarchy <= DefaultRole
                    .get_default_hierarchy(DefaultRole.MANAGER) 
                or db_client.created_by == current_user.id
            )
        )

        return ClientResponse(data=ClientRead(**db_client.model_dump()))


@router.get("/client", response_model=ClientReadList)
def query_clients(
    name: str | None = None,
    person_code: str | None = None,
    enterprise_code: str | None = None,
    db_session: Session = Depends(get_db),
    current_user: UserRead = Depends(authenticate_user),
    ) -> ClientReadList:

    authorize_user(
        user=current_user,
        operation_scopes=[
            DefaultScope.ALL.value, 
            DefaultScope.SELLS.value],
        operation_hierarchy_order=DefaultRole.get_default_hierarchy(
            DefaultRole.COLLABORATOR
        )
    )

    with db_session:
        query = select(Client).where(col(Client.enterprise_id) == current_user.enterprise_id)

        if name is not None:
            query = query.where(col(Client.name) == name)
        if person_code is not None:
            query = query.where(col(Client.person_code) == person_code)
        if enterprise_code is not None:
            query = query.where(col(Client.enterprise_code) == enterprise_code)

        db_clients = db_session.exec(query).all()

        if db_clients is None:
            raise HTTPException(status_code=404, detail="No clients found")

        resp = ClientReadList(data=[ClientRead(**db_client.model_dump()) for db_client in db_clients])

        authorize_user(
            user=current_user,
            operation_scopes=[
                DefaultScope.ALL.value, 
                DefaultScope.SELLS.value],
            operation_hierarchy_order=DefaultRole.get_default_hierarchy(
                DefaultRole.COLLABORATOR
            ),
            custom_checks=(
                current_user.role.hierarchy <= DefaultRole
                    .get_default_hierarchy(DefaultRole.MANAGER) 
                or all(
                    [x.created_by == current_user.id for x in db_clients]
                )
            )
        )

        return resp


@router.delete("/client/{client_id}", response_model=DefaultResponse)
def delete_client(
    client_id: int,
    db_session: Session = Depends(get_db),
    current_user: UserRead = Depends(authenticate_user),
    ) -> DefaultResponse:
    authorize_user(
        user=current_user,
        operation_scopes=[
            DefaultScope.ALL.value, 
            DefaultScope.SELLS.value],
        operation_hierarchy_order=DefaultRole.get_default_hierarchy(
            DefaultRole.MANAGER)
    )
    with db_session:
        db_client = db_session.exec(
            select(Client)
                .where(col(Client.id) == client_id)
                .where(col(Client.enterprise_id) == current_user.enterprise_id)
        ).first()

        if db_client is None:
            raise HTTPException(status_code=404, detail="Client not found")

        db_session.delete(db_client)
        db_session.commit()

        return DefaultResponse()


@router.post("/", response_model=SellDetailResponse)
def create_sell(
    sell: SellCreate,
    db_session: Session = Depends(get_db),
    current_user: UserRead = Depends(authenticate_user),
) -> SellDetailResponse:
    print('Sell detail')

    authorize_user(
        user=current_user,
        operation_scopes=[DefaultScope.SELLS.value, "All"],
        operation_hierarchy_order=DefaultRole.get_default_hierarchy(
            DefaultRole.MANAGER
        )
    )

    with db_session:
        stock_product_user = db_session.exec(
            select(BaseProduct, User)
                .where(col(BaseProduct.id) == sell.product_id)
                .join(User, onclause=col(BaseProduct.created_by) == col(User.id))
                .with_for_update(),
        ).first()

        if stock_product_user is None:
            print(f'Stock product not found product_id: {sell.product_id}')
            raise HTTPException(status_code=404, detail="Product not found")

        stock_product, user = stock_product_user

        if user.enterprise_id != current_user.enterprise_id:
            print('Enterprise id:', user.enterprise_id, 'Current user enterprise id:', current_user.enterprise_id)
            raise HTTPException(status_code=404, detail="Product not found")

        if stock_product.price is None:
            raise HTTPException(status_code=400, detail="Product has no price")

        if stock_product.stock < sell.quantity:
            raise HTTPException(status_code=400, detail="Not enough stock")

        stock_product.stock -= sell.quantity
        db_session.add(stock_product)

        db_sell = Sell(**sell.model_dump())

        db_session.add(db_sell)
        db_session.commit()
        db_session.refresh(db_sell)

        return SellDetailResponse(data=BaseSell(**db_sell.model_dump()))


@router.post("/me", response_model=SellDetailResponse)
def create_my_sell(
    sell: SellCreateMe,
    db_session: Session = Depends(get_db),
    current_user: UserRead = Depends(authenticate_user),
) -> SellDetailResponse:
    with db_session:

        print(f'Sell id: {sell.product_id}, Enterprise id: {current_user.enterprise_id}')
        stock_product = db_session.exec(
            select(BaseProduct)
                .where(col(BaseProduct.id) == sell.product_id)
                .with_for_update(),
        ).first()

        if stock_product is None or stock_product.enterprise_id != current_user.enterprise_id:
            raise HTTPException(status_code=404, detail="Product not found")

        if stock_product.price is None:
            raise HTTPException(status_code=400, detail="Product has no price")

        if stock_product.stock < sell.quantity:
            raise HTTPException(status_code=400, detail="Not enough stock")

        stock_product.stock -= sell.quantity
        db_session.add(stock_product)

        db_sell = Sell(
            **sell.model_dump(),
            user_id=current_user.id
        )
        db_session.add(db_sell)
        db_session.commit()
        db_session.refresh(db_sell)

        return SellDetailResponse(data=BaseSell(**db_sell.model_dump()))


@router.get("/me", response_model=SellsResponse)
def get_my_sells(
    db_session: Session = Depends(get_db),
    current_user: UserRead = Depends(authenticate_user),
) -> SellsResponse:
    with db_session:
        db_user = db_session.get(User, current_user.id)

        if db_user is None:
            raise HTTPException(status_code=404, detail="User not found")

        print('DB User sells:', db_user.sells)

        sells = list(map(lambda x: BaseSell(**x.model_dump()), db_user.sells \
            if db_user.sells is not None else []))
        return SellsResponse(data=sells)


@router.get("/", response_model=UserSellsListResponse)
def query_sells(
    user_ids: str | None = None,
    db_session: Session = Depends(get_db),
    current_user: UserRead = Depends(authenticate_user),
) -> UserSellsListResponse:

    authorize_user(
        user=current_user,
        operation_scopes=["Sells", "All"],
        operation_hierarchy_order=DefaultRole.get_default_hierarchy(
            DefaultRole.MANAGER
        )
    )

    with db_session:
        user_query = select(User).where(col(User.enterprise_id) == current_user.enterprise_id)
        if user_ids is not None:
            ids = map(int, user_ids.split(","))
            user_query = user_query.where(col(User.id).in_(ids))

        resp = db_session.exec(user_query).all()

        if resp is None:
            raise HTTPException(status_code=404, detail='No sells found')

        def sells_from_user(x: User):
            return list(
                map(
                    lambda y: BaseSell(**y.model_dump()), 
                    x.sells if x.sells is not None else []
                 )
            )

        user_sells = list(
            map(lambda x: UserSells(
                id=x.id, 
                username=x.username, 
                sells=sells_from_user(x)
            ), 
            resp
        ))

        return UserSellsListResponse(data=user_sells)


@router.get("/{user_id}/{client_id}/{product_id}", response_model=SellDetailResponse)
def read_sell(
    user_id: int,
    client_id: int,
    product_id: int,
    db_session: Session = Depends(get_db),
    current_user: UserRead = Depends(authenticate_user),
) -> SellDetailResponse:
    with db_session:
        clause= (
            and_(
                col(User.id) == current_user.id,
                col(User.enterprise_id) == current_user.enterprise_id
            )
        )

        sell_ex = db_session.exec(
            select(Sell, col(User.enterprise_id)) \
                .where(col(Sell.user_id) == user_id) \
                .where(col(Sell.client_id) == client_id) \
                .where(col(Sell.product_id) == product_id)
                .join(User, onclause=clause)
        ).first()

        if sell_ex is None:
            raise HTTPException(status_code=404, detail="Sell not found")

        sell, _ = sell_ex

        authorize_user(
            user=current_user,
            operation_scopes=["Sells", "All"],
            operation_hierarchy_order=DefaultRole.get_default_hierarchy(
                DefaultRole.COLLABORATOR
            ),
            custom_checks=(
                current_user.role.hierarchy <= DefaultRole
                    .get_default_hierarchy(DefaultRole.MANAGER) 
                or sell.user_id == current_user.id
            )
        )

        return SellDetailResponse(data=sell)


@router.delete("/{user_id}/{client_id}/{product_id}", response_model=DefaultResponse)
def delete_sell(
    user_id: int,
    client_id: int,
    product_id: int,
    db_session: Session = Depends(get_db),
    current_user: UserRead = Depends(authenticate_user),
) -> DefaultResponse:
    authorize_user(
        user=current_user,
        operation_scopes=["Sells", "All"],
        operation_hierarchy_order=DefaultRole.get_default_hierarchy(
            DefaultRole.MANAGER
        )
    )
    with db_session:
        sell_product = db_session.exec(
            select(Sell, BaseProduct).where(
                and_(
                    col(Sell.user_id) == user_id ,
                    col(Sell.product_id) == product_id,
                    col(Sell.client_id) == client_id
                )
            ).where(
                User.enterprise_id == current_user.enterprise_id
            ).join(
                BaseProduct, 
                onclause=col(Sell.product_id) == col(BaseProduct.id)
            ).join(
                User,
                onclause=col(Sell.user_id) == col(User.id)
            ).with_for_update(),
        ).first()

        if sell_product is None:
            raise HTTPException(status_code=404, detail="Sell not found")

        sell, prod = sell_product

        if sell is None or prod is None:
            raise HTTPException(status_code=404, detail="Sell not found")

        prod.stock += sell.quantity

        db_session.add(prod)
        db_session.delete(sell)
        db_session.commit()

    return DefaultResponse()
