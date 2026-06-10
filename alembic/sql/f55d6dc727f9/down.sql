-- Удаление внешнего ключа
ALTER TABLE catalog.products DROP CONSTRAINT IF EXISTS fk_products_category_id;

-- Удаление таблиц
DROP TABLE IF EXISTS catalog.products CASCADE;
DROP TABLE IF EXISTS catalog.warehouses CASCADE;
DROP TABLE IF EXISTS catalog.product_categories CASCADE;

-- Удаление схемы
DROP SCHEMA IF EXISTS catalog CASCADE;
DROP SCHEMA IF EXISTS sales CASCADE;