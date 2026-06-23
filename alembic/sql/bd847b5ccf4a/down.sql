-- Down миграция для юзеров catalog_manager, sales_manager

-- 1. Откатываем поле created_by в orders
ALTER TABLE sales.orders DROP CONSTRAINT fk_orders_created_by;
ALTER TABLE sales.orders DROP COLUMN created_by;

-- 2. Откатываем доступ на чтение catalog для PUBLIC
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog REVOKE SELECT ON TABLES FROM PUBLIC;
REVOKE SELECT ON ALL TABLES IN SCHEMA catalog FROM PUBLIC;
REVOKE USAGE ON SCHEMA catalog FROM PUBLIC;

-- 3. Откатываем права sales_manager на схему sales
ALTER DEFAULT PRIVILEGES IN SCHEMA sales REVOKE ALL PRIVILEGES ON SEQUENCES FROM sales_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales REVOKE ALL PRIVILEGES ON TABLES FROM sales_manager;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA sales FROM sales_manager;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA sales FROM sales_manager;
REVOKE USAGE ON SCHEMA sales FROM sales_manager;

-- 4. Откатываем права catalog_manager на схему catalog
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog REVOKE ALL PRIVILEGES ON SEQUENCES FROM catalog_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog REVOKE ALL PRIVILEGES ON TABLES FROM catalog_manager;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA catalog FROM catalog_manager;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA catalog FROM catalog_manager;
REVOKE USAGE ON SCHEMA catalog FROM catalog_manager;