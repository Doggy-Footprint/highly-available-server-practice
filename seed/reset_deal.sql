-- 딜 수량·주문 초기화 (§4 `make reset-deal`). 스파이크 실험 전에 반드시 돌린다.
--
-- "딜 주문" 을 어떻게 식별하는가:
--   seed 가 딜 전용 상품(products 뒤쪽 20개)을 따로 떼어 두었고, 일반 주문은 그 상품을
--   절대 참조하지 않는다. 따라서 "deals.product_id 를 참조하는 order_items" = 딜 판매분이다.
--   id 범위를 하드코딩하지 않고 deals 와 조인해서 찾는다.
--
-- VACUUM 은 일부러 하지 않는다:
--   반복 스파이크로 쌓인 dead tuple 이 P2-12(핫로우 bloat)의 관찰 대상이다.
--   여기서 청소해 버리면 그 이슈가 영영 재현되지 않는다.
--   P2-12 측정 전에는 pg_stat_user_tables 로 dead ratio 를 먼저 확인할 것.

\set ON_ERROR_STOP on

BEGIN;

CREATE TEMP TABLE _deal_orders ON COMMIT DROP AS
SELECT DISTINCT oi.order_id
FROM order_items oi
JOIN deals d ON d.product_id = oi.product_id;

DELETE FROM payments    WHERE order_id IN (SELECT order_id FROM _deal_orders);
DELETE FROM order_items WHERE order_id IN (SELECT order_id FROM _deal_orders);
DELETE FROM orders      WHERE id       IN (SELECT order_id FROM _deal_orders);

UPDATE deals SET remaining_qty = total_qty;

COMMIT;

\echo ''
\echo '--- reset 결과 ---'
SELECT id AS deal_id, product_id, total_qty, remaining_qty, opens_at, closes_at
FROM deals
ORDER BY id;
