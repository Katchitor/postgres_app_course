-- Down миграция

-- Миграция для поля created_by в orders
ALTER TABLE sales.orders DROP CONSTRAINT fk_orders_created_by;
ALTER TABLE sales.orders DROP COLUMN created_by;

-- Отзываем права
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA catalog FROM catalog_manager;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA catalog FROM catalog_manager;
REVOKE USAGE ON SCHEMA catalog FROM catalog_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog REVOKE ALL PRIVILEGES ON TABLES FROM catalog_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog REVOKE ALL PRIVILEGES ON SEQUENCES FROM catalog_manager;

REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA sales FROM sales_manager;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA sales FROM sales_manager;
REVOKE USAGE ON SCHEMA sales FROM sales_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales REVOKE ALL PRIVILEGES ON TABLES FROM sales_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales REVOKE ALL PRIVILEGES ON SEQUENCES FROM sales_manager;

REVOKE SELECT ON ALL TABLES IN SCHEMA catalog FROM sales_manager;
REVOKE USAGE ON SCHEMA catalog FROM sales_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog REVOKE SELECT ON TABLES FROM sales_manager;

-- Удаляем таблицы в обратном порядке (сначала дочерние, потом родительские)
DROP TABLE IF EXISTS sales.order_items CASCADE;
DROP TABLE IF EXISTS sales.orders CASCADE;
DROP TABLE IF EXISTS catalog.products CASCADE;
DROP TABLE IF EXISTS catalog.product_categories CASCADE;
DROP TABLE IF EXISTS catalog.warehouses CASCADE;

-- Удаляем схемы
DROP SCHEMA IF EXISTS sales CASCADE;
DROP SCHEMA IF EXISTS catalog CASCADE;