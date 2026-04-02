from uuid import UUID

from fastapi import APIRouter, Depends
from src.db.models import DBUser
from src.routes.v1.orders.schema import OrderCreateInput, OrderOutput, OrderUpdateInput
from src.routes.v1.orders.service import OrderService, get_order_service
from src.utils.auth import authenticate_user

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderOutput, status_code=201)
async def create_order(
    order_input: OrderCreateInput,
    order_service: OrderService = Depends(get_order_service),
    current_user: DBUser = Depends(authenticate_user),
):
    order = await order_service.create(data=order_input, user_id=current_user.id)
    return OrderOutput(**order.model_dump())


@router.get("", response_model=list[OrderOutput])
async def list_orders(
    order_service: OrderService = Depends(get_order_service),
    current_user: DBUser = Depends(authenticate_user),
):
    orders = await order_service.list_by_user(user_id=current_user.id)
    return [OrderOutput(**order.model_dump()) for order in orders]


@router.get("/{order_id}", response_model=OrderOutput)
async def get_order(
    order_id: UUID,
    order_service: OrderService = Depends(get_order_service),
    current_user: DBUser = Depends(authenticate_user),
):
    order = await order_service.retrieve_by_user(order_id=order_id, user_id=current_user.id)
    return OrderOutput(**order.model_dump())


@router.patch("/{order_id}", response_model=OrderOutput)
async def update_order(
    order_id: UUID,
    update_input: OrderUpdateInput,
    order_service: OrderService = Depends(get_order_service),
    current_user: DBUser = Depends(authenticate_user),
):
    order = await order_service.update(order_id=order_id, user_id=current_user.id, data=update_input)
    return OrderOutput(**order.model_dump())


@router.delete("/{order_id}", status_code=204)
async def delete_order(
    order_id: UUID,
    order_service: OrderService = Depends(get_order_service),
    current_user: DBUser = Depends(authenticate_user),
):
    await order_service.delete(order_id=order_id, user_id=current_user.id)
