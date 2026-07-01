-- Создаем таблицу городов
CREATE TABLE IF NOT EXISTS catalog.cities (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

-- Добавляем города
INSERT INTO catalog.cities (name) VALUES 
    ('Москва'),
    ('Санкт-Петербург'),
    ('Новосибирск'),
    ('Екатеринбург'),
    ('Казань'),
    ('Нижний Новгород'),
    ('Челябинск'),
    ('Самара'),
    ('Омск'),
    ('Ростов-на-Дону'),
    ('Уфа'),
    ('Красноярск'),
    ('Воронеж'),
    ('Пермь'),
    ('Волгоград')
ON CONFLICT (name) DO NOTHING;

-- Добавляем поле city_id
ALTER TABLE catalog.warehouses ADD COLUMN city_id INTEGER;

-- Добавляем внешний ключ
ALTER TABLE catalog.warehouses ADD CONSTRAINT fk_warehouses_city_id 
    FOREIGN KEY (city_id) REFERENCES catalog.cities(id);

-- Переносим данные из city в city_id
UPDATE catalog.warehouses w
SET city_id = c.id
FROM catalog.cities c
WHERE w.city = c.name;

-- Делаем city_id NOT NULL
ALTER TABLE catalog.warehouses ALTER COLUMN city_id SET NOT NULL;

-- Удаляем старое поле city
ALTER TABLE catalog.warehouses DROP COLUMN city;

-- ============ СОЗДАНИЕ СХЕМЫ INVENTORY ============
CREATE SCHEMA IF NOT EXISTS inventory;

-- ============ ТАБЛИЦА ROUTES ============
CREATE TABLE IF NOT EXISTS inventory.routes (
    from_city_id INTEGER NOT NULL,
    to_city_id INTEGER NOT NULL,
    duration INTERVAL NOT NULL,
    min_amount NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (from_city_id, to_city_id),
    FOREIGN KEY (from_city_id) REFERENCES catalog.cities(id) ON DELETE CASCADE,
    FOREIGN KEY (to_city_id) REFERENCES catalog.cities(id) ON DELETE CASCADE
);

-- ============ ТАБЛИЦА STOCK ============
CREATE SEQUENCE IF NOT EXISTS inventory.stock_id_seq;

CREATE TABLE inventory.stock (
    warehouse_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (warehouse_id, product_id),
    FOREIGN KEY (warehouse_id) REFERENCES catalog.warehouses(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES catalog.products(id) ON DELETE CASCADE
);

-- ============ ТАБЛИЦА RESERVES ============
CREATE SEQUENCE IF NOT EXISTS inventory.reserves_id_seq;

CREATE TABLE IF NOT EXISTS inventory.reserves (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES sales.orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES catalog.products(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    UNIQUE (order_id, product_id)
);

-- ============ ТАБЛИЦА DELIVERIES ============
CREATE SEQUENCE IF NOT EXISTS inventory.deliveries_id_seq;

CREATE TABLE IF NOT EXISTS inventory.deliveries (
    order_id INTEGER PRIMARY KEY,
    status VARCHAR(50) NOT NULL DEFAULT 'planned',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    shipped_at TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES sales.orders(id) ON DELETE CASCADE,
    CONSTRAINT chk_deliveries_status CHECK (status IN ('planned', 'shipping', 'shipped'))
);

-- ============ ТАБЛИЦА DELIVERY_ITEMS ============
CREATE SEQUENCE IF NOT EXISTS inventory.delivery_items_id_seq;

CREATE TABLE IF NOT EXISTS inventory.delivery_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'planned',
    FOREIGN KEY (order_id) REFERENCES inventory.deliveries(order_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES catalog.products(id) ON DELETE CASCADE,
    CONSTRAINT chk_delivery_items_status CHECK (status IN ('planned', 'shipped'))
);

-- ============ ТАБЛИЦА TRANSFERS ============
CREATE SEQUENCE IF NOT EXISTS inventory.transfers_id_seq;

CREATE TABLE IF NOT EXISTS inventory.transfers (
    id SERIAL PRIMARY KEY,
    from_warehouse_id INTEGER NOT NULL,
    to_warehouse_id INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'planned',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    arriving_at TIMESTAMP,
    received_at TIMESTAMP,
    FOREIGN KEY (from_warehouse_id) REFERENCES catalog.warehouses(id) ON DELETE CASCADE,
    FOREIGN KEY (to_warehouse_id) REFERENCES catalog.warehouses(id) ON DELETE CASCADE,
    CONSTRAINT chk_transfers_status CHECK (status IN ('planned', 'shipping', 'in_transit', 'arrived', 'received'))
);

-- ============ ТАБЛИЦА TRANSFER_ITEMS ============
CREATE SEQUENCE IF NOT EXISTS inventory.transfer_items_id_seq;

CREATE TABLE IF NOT EXISTS inventory.transfer_items (
    id SERIAL PRIMARY KEY,
    transfer_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'planned',
    reserve_id INTEGER,
    requested_by INTEGER NOT NULL,
    FOREIGN KEY (transfer_id) REFERENCES inventory.transfers(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES catalog.products(id) ON DELETE CASCADE,
    FOREIGN KEY (requested_by) REFERENCES auth.users(id) ON DELETE CASCADE,
    CONSTRAINT chk_transfer_items_status CHECK (status IN ('planned', 'shipped', 'received'))
);

-- ============ ПРАВА ДЛЯ INVENTORY_MANAGER ============
-- Полный доступ к схеме inventory
GRANT USAGE ON SCHEMA inventory TO inventory_manager;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA inventory TO inventory_manager;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA inventory TO inventory_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA inventory GRANT ALL PRIVILEGES ON TABLES TO inventory_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA inventory GRANT ALL PRIVILEGES ON SEQUENCES TO inventory_manager;

-- Чтение sales
GRANT USAGE ON SCHEMA sales TO inventory_manager;
GRANT SELECT ON ALL TABLES IN SCHEMA sales TO inventory_manager;
ALTER DEFAULT PRIVILEGES IN SCHEMA sales GRANT SELECT ON TABLES TO inventory_manager;

-- Обновление ТОЛЬКО статуса заказов
GRANT UPDATE (status) ON sales.orders TO inventory_manager;

-- ============ ПРАВА ДЛЯ WORKER ============
-- Доступ к схеме inventory
GRANT USAGE ON SCHEMA inventory TO worker;

-- Все права на STOCK
GRANT ALL PRIVILEGES ON inventory.stock TO worker;

-- Обновление RESERVES
GRANT SELECT, INSERT, UPDATE, DELETE ON inventory.reserves TO worker;
GRANT USAGE ON inventory.reserves_id_seq TO worker;

-- Обновление DELIVERIES (только статусы и даты)
GRANT SELECT, UPDATE (status, shipped_at) ON inventory.deliveries TO worker;
GRANT SELECT, UPDATE (status) ON inventory.delivery_items TO worker;

-- Обновление TRANSFERS (только статусы и даты)
GRANT SELECT, UPDATE (status, started_at, arriving_at, received_at) ON inventory.transfers TO worker;
GRANT SELECT, UPDATE (status) ON inventory.transfer_items TO worker;

-- Чтение всех таблиц inventory
GRANT SELECT ON ALL TABLES IN SCHEMA inventory TO worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA inventory GRANT SELECT ON TABLES TO worker;

-- Последовательности для worker
GRANT USAGE ON ALL SEQUENCES IN SCHEMA inventory TO worker;
ALTER DEFAULT PRIVILEGES IN SCHEMA inventory GRANT USAGE ON SEQUENCES TO worker;