-- invariant: 같은 요청을 두 번 보내도 주문은 하나만 생긴다 (P2-04 완료 기준).
--
-- Phase 0 에는 idempotency_key 컬럼이 없다 (일부러 넣지 않았다 — §1). 그래서 중복을
-- 컬럼으로 못 찾고, "같은 유저가 같은 아이템 구성으로 몇 초 안에 만든 주문" 을 짝지어 센다.
-- P2-04 fix 로 Idempotency-Key + unique 제약이 들어가면 이 쿼리는 자연히 0 을 반환한다.
--
-- 최근 30분만 본다. seed 된 300만 건 히스토리에는 우연히 같은 구성이 얼마든지 있고,
-- 그건 중복 주문이 아니라 그냥 데이터다.
--
-- 느린 게 정상이다: orders.created_at 에도 order_items.order_id 에도 인덱스가 없어서
-- seq scan 이 돈다. 부하가 끝난 뒤에 돌리는 검증이므로 신경쓰지 않는다.
--
-- 사용: make check S=dup_orders

\set ON_ERROR_STOP on

\set window_minutes 30
\set burst_seconds 5

CREATE OR REPLACE TEMP VIEW _recent_orders AS
SELECT o.id,
       o.user_id,
       o.created_at,
       o.total_amount,
       md5(string_agg(oi.product_id::text || 'x' || oi.qty::text, ',' ORDER BY oi.product_id))
           AS items_fp
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.created_at > now() - (:'window_minutes' || ' minutes')::interval
GROUP BY o.id, o.user_id, o.created_at, o.total_amount;

CREATE OR REPLACE TEMP VIEW _dup_pairs AS
SELECT a.user_id,
       a.items_fp,
       a.id  AS first_order_id,
       b.id  AS dup_order_id,
       b.created_at - a.created_at AS gap
FROM _recent_orders a
JOIN _recent_orders b
  ON b.user_id = a.user_id
 AND b.items_fp = a.items_fp
 AND b.id > a.id
 AND b.created_at - a.created_at < (:'burst_seconds' || ' seconds')::interval;

\echo ''
\echo '--- 중복으로 의심되는 주문 짝 (상위 20) ---'
SELECT user_id, first_order_id, dup_order_id, gap
FROM _dup_pairs
ORDER BY gap
LIMIT 20;

\echo ''
\echo '--- 판정: duplicate_order_pairs = 0 이어야 통과 ---'
SELECT count(*)                       AS duplicate_order_pairs,
       count(DISTINCT user_id)        AS affected_users
FROM _dup_pairs;
