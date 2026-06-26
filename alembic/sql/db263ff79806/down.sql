-- ============ ОТКАТ ПРАВ WORKER ============
-- Отзываем права на последовательности в inventory
ALTER DEFAULT PRIVILEGES IN SCHEMA inventory REVOKE USAGE ON SEQUENCES FROM worker;
REVOKE USAGE ON ALL SEQUENCES IN SCHEMA inventory FROM worker;

-- Отзываем права на чтение таблиц inventory
ALTER DEFAULT PRIVILEGES IN SCHEMA inventory REVOKE SELECT ON TABLES FROM worker;
REVOKE SELECT ON ALL TABLES IN SCHEMA inventory FROM worker;

-- Отзываем права на обновление transfer_items
REVOKE UPDATE (status) ON inventory.transfer_items FROM worker;

-- Отзываем права на обновление transfers (статусы и даты)
REVOKE UPDATE (status, started_at, arriving_at, received_at) ON inventory.transfers FROM worker;

-- Отзываем права на обновление delivery_items
REVOKE UPDATE (status) ON inventory.delivery_items FROM worker;

-- Отзываем права на обновление deliveries (статусы и даты)
REVOKE UPDATE (status, shipped_at) ON inventory.deliveries FROM worker;

-- Отзываем права на reserves
REVOKE USAGE ON inventory.reserves_id_seq FROM worker;
REVOKE SELECT, INSERT, UPDATE, DELETE ON inventory.reserves FROM worker;

-- Отзываем все права на stock
REVOKE ALL PRIVILEGES ON inventory.stock FROM worker;

-- Отзываем базовый доступ к схеме inventory
REVOKE USAGE ON SCHEMA inventory FROM worker;

-- ============ ОТКАТ ПРАВ INVENTORY_MANAGER ============
-- Отзываем права на обновление статуса заказов
REVOKE UPDATE (status) ON sales.orders FROM inventory_manager;

-- Отзываем права на чтение sales
ALTER DEFAULT PRIVILEGES IN SCHEMA sales REVOKE SELECT ON TABLES FROM inventory_manager;
REVOKE SELECT ON ALL TABLES IN SCHEMA sales FROM inventory_manager;
REVOKE USAGE ON SCHEMA sales FROM inventory_manager;

-- Отзываем права на схему inventory
ALTER DEFAULT PRIVILEGES IN SCHEMA inventory REVOKE ALL PRIVILEGES ON SEQUENCES FROM inventory_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA inventory REVOKE ALL PRIVILEGES ON TABLES FROM inventory_manager;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA inventory FROM inventory_manager;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA inventory FROM inventory_manager;
REVOKE USAGE ON SCHEMA inventory FROM inventory_manager;

-- ============ УДАЛЕНИЕ ТАБЛИЦ INVENTORY ============
DROP TABLE IF EXISTS inventory.transfer_items;
DROP TABLE IF EXISTS inventory.transfers;
DROP TABLE IF EXISTS inventory.delivery_items;
DROP TABLE IF EXISTS inventory.deliveries;
DROP TABLE IF EXISTS inventory.reserves;
DROP TABLE IF EXISTS inventory.stock;
DROP TABLE IF EXISTS inventory.routes;

-- ============ УДАЛЕНИЕ ПОСЛЕДОВАТЕЛЬНОСТЕЙ INVENTORY ============
DROP SEQUENCE IF EXISTS inventory.stock_id_seq;
DROP SEQUENCE IF EXISTS inventory.reserves_id_seq;
DROP SEQUENCE IF EXISTS inventory.deliveries_id_seq;
DROP SEQUENCE IF EXISTS inventory.delivery_items_id_seq;
DROP SEQUENCE IF EXISTS inventory.transfers_id_seq;
DROP SEQUENCE IF EXISTS inventory.transfer_items_id_seq;

-- ============ УДАЛЕНИЕ СХЕМЫ INVENTORY ============
DROP SCHEMA IF EXISTS inventory CASCADE;

-- ============ ВОССТАНОВЛЕНИЕ ТАБЛИЦЫ WAREHOUSES ============
-- Восстанавливаем поле city
ALTER TABLE catalog.warehouses ADD COLUMN city TEXT;

-- Заполняем city из city_id
UPDATE catalog.warehouses w
SET city = c.name
FROM catalog.cities c
WHERE w.city_id = c.id;

-- Делаем city NOT NULL
ALTER TABLE catalog.warehouses ALTER COLUMN city SET NOT NULL;

-- Удаляем внешний ключ
ALTER TABLE catalog.warehouses DROP CONSTRAINT IF EXISTS fk_warehouses_city_id;

-- Удаляем поле city_id
ALTER TABLE catalog.warehouses DROP COLUMN city_id;

-- ============ УДАЛЕНИЕ ТАБЛИЦЫ CITIES ============
-- Удаляем данные и таблицу
TRUNCATE TABLE catalog.cities RESTART IDENTITY CASCADE;
DROP TABLE IF EXISTS catalog.cities;