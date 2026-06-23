-- Up миграция для юзеров catalog_manager, sales_manager

--  catalog_manager — полный доступ к схеме catalog
GRANT USAGE ON SCHEMA catalog TO catalog_manager;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA catalog TO catalog_manager;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA catalog TO catalog_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog GRANT ALL PRIVILEGES ON TABLES TO catalog_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog GRANT ALL PRIVILEGES ON SEQUENCES TO catalog_manager;

--  sales_manager — полный доступ к схеме sales
GRANT USAGE ON SCHEMA sales TO sales_manager;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA sales TO sales_manager;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA sales TO sales_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales GRANT ALL PRIVILEGES ON TABLES TO sales_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales GRANT ALL PRIVILEGES ON SEQUENCES TO sales_manager;

--  Доступ на чтение catalog для ВСЕХ (включая будущие роли)
GRANT USAGE ON SCHEMA catalog TO PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA catalog TO PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA catalog GRANT SELECT ON TABLES TO PUBLIC;

-- Миграция для поля created_by в orders
ALTER TABLE sales.orders ADD COLUMN created_by INTEGER;

ALTER TABLE sales.orders ADD CONSTRAINT fk_orders_created_by
    FOREIGN KEY (created_by) REFERENCES auth.users(id);

UPDATE sales.orders
SET created_by = (SELECT id FROM auth.users WHERE username = 'app_user')
WHERE created_by IS NULL;

ALTER TABLE sales.orders ALTER COLUMN created_by SET NOT NULL;