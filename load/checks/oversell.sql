-- invariant: 딜 판매 수량은 total_qty 를 절대 넘지 않는다 (P2-01 / P2-02 완료 기준).
--
-- 두 가지를 본다:
--   oversold        — 실제로 판 수량이 딜 정원을 넘었는가. 이게 0 이 아니면 실패다.
--   ledger_mismatch — remaining_qty 가 깎인 만큼과 실제 판 수량이 어긋나는가.
--                     check-then-act(P2-01)에서는 재고를 깎고 주문을 못 만들거나
--                     그 반대가 생길 수 있어서, oversold 가 0 이어도 장부가 안 맞을 수 있다.
--
-- 사용: make check S=oversell

\set ON_ERROR_STOP on

CREATE OR REPLACE TEMP VIEW _deal_sales AS
SELECT d.id AS deal_id,
       d.product_id,
       d.total_qty,
       d.remaining_qty,
       COALESCE(SUM(oi.qty) FILTER (WHERE o.status <> 'FAILED'), 0)::bigint AS sold_qty
FROM deals d
LEFT JOIN order_items oi ON oi.product_id = d.product_id
LEFT JOIN orders o ON o.id = oi.order_id
GROUP BY d.id, d.product_id, d.total_qty, d.remaining_qty;

\echo ''
\echo '--- 딜별 상세 (판매 흔적이 있는 딜만) ---'
SELECT deal_id,
       total_qty,
       remaining_qty,
       total_qty - remaining_qty       AS claimed_qty,
       sold_qty,
       sold_qty - (total_qty - remaining_qty) AS ledger_mismatch,
       GREATEST(sold_qty - total_qty, 0)      AS oversold
FROM _deal_sales
WHERE sold_qty > 0 OR remaining_qty < total_qty
ORDER BY oversold DESC, deal_id;

\echo ''
\echo '--- 판정: 둘 다 0 이어야 통과 ---'
SELECT count(*) FILTER (WHERE sold_qty > total_qty)                     AS oversold_deals,
       count(*) FILTER (WHERE sold_qty <> total_qty - remaining_qty)    AS ledger_mismatch_deals
FROM _deal_sales;
