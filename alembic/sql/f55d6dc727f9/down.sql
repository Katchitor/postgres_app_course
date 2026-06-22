-- Down миграция для catalog и sales схем

-- Удаляем таблицы в обратном порядке (сначала дочерние, потом родительские)
DROP TABLE IF EXISTS sales.order_items CASCADE;
DROP TABLE IF EXISTS sales.orders CASCADE;
DROP TABLE IF EXISTS catalog.products CASCADE;
DROP TABLE IF EXISTS catalog.product_categories CASCADE;
DROP TABLE IF EXISTS catalog.warehouses CASCADE;

-- Удаляем схемы
DROP SCHEMA IF EXISTS sales CASCADE;
DROP SCHEMA IF EXISTS catalog CASCADE;