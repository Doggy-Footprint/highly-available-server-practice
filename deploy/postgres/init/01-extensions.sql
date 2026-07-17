-- 관측용 확장 (§9). shared_preload_libraries 로 라이브러리는 이미 로드되어 있고,
-- 뷰를 쓰려면 데이터베이스마다 CREATE EXTENSION 이 필요하다.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- pg_trgm 은 여기서 만들지 않는다.
-- P1-03(검색 인덱스 없음)의 fix 마이그레이션에서 GIN 인덱스와 함께 도입한다.
