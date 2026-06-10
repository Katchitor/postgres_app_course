-- Создание схемы catalog
CREATE SCHEMA catalog AUTHORIZATION app_user;

CREATE TABLE catalog.product_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE catalog.products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    category_id INTEGER NOT NULL
);

CREATE TABLE catalog.warehouses (
    id SERIAL PRIMARY KEY,
    city VARCHAR(100) NOT NULL,
    address VARCHAR(255) NOT NULL,
    label VARCHAR(100),
    is_central BOOLEAN NOT NULL DEFAULT FALSE
);

ALTER TABLE catalog.products
ADD CONSTRAINT fk_products_category_id
FOREIGN KEY (category_id) REFERENCES catalog.product_categories(id);

-- Создание схемы sales
CREATE SCHEMA IF NOT EXISTS sales AUTHORIZATION app_user;

-- Таблица заказов
CREATE TABLE sales.orders (
    id SERIAL PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'unpublished',
    total_amount DECIMAL(10, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    warehouse_id INTEGER NOT NULL,
    CONSTRAINT orders_status_check CHECK (status IN ('unpublished', 'new', 'processing', 'pending', 'packing', 'shipped'))
);

-- Таблица товаров в заказе
CREATE TABLE sales.order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0)
);

-- Добавление внешних ключей
ALTER TABLE sales.order_items
ADD CONSTRAINT fk_order_items_order_id
FOREIGN KEY (order_id) REFERENCES sales.orders(id) ON DELETE CASCADE;

ALTER TABLE sales.order_items
ADD CONSTRAINT fk_order_items_product_id
FOREIGN KEY (product_id) REFERENCES catalog.products(id) ON DELETE RESTRICT;

ALTER TABLE sales.orders
ADD CONSTRAINT fk_orders_warehouse_id
FOREIGN KEY (warehouse_id) REFERENCES catalog.warehouses(id) ON DELETE RESTRICT;