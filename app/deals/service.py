from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deals import repository
from app.models import Deal, Order, User


async def purchase(session: AsyncSession, user: User, deal_id: int, qty: int) -> tuple[Order, Deal]:
    deal = await repository.get_deal(session, deal_id)
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deal not found")

    # INTENDED-ISSUE: P2-01
    # check-then-act: 아래에서 remaining_qty 를 읽어 검사한 뒤, 주문 생성과 재고 차감
    # UPDATE 까지의 사이에 다른 요청이 끼어든다. 동시 요청들이 같은 remaining 값을 보고
    # 전부 이 검사를 통과 → 주문은 다 만들어지고 재고는 음수로 → oversell.
    # 조건부 원자 UPDATE(`... AND remaining_qty >= qty`)가 아니라서 막지 못한다.
    # fix 1차: decrement 를 가드 있는 원자 UPDATE 로 바꾸고 rowcount 로 판정.
    if deal.remaining_qty < qty:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="sold out")

    order = await repository.create_deal_order(session, user.id, deal, qty)
    await repository.decrement_remaining(session, deal_id, qty)
    await session.commit()
    await session.refresh(deal)
    return order, deal
