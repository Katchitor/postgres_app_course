-- Up миграция для catalog и sales схем

-- Создание схемы catalog
CREATE SCHEMA IF NOT EXISTS catalog AUTHORIZATION app_user;

CREATE TABLE IF NOT EXISTS catalog.product_categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS catalog.products (
    id SERIAL PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    category_id INTEGER NOT NULL,
    CONSTRAINT fk_products_category_id FOREIGN KEY (category_id) REFERENCES catalog.product_categories(id)
);

CREATE TABLE IF NOT EXISTS catalog.warehouses (
    id SERIAL PRIMARY KEY,
    city TEXT NOT NULL,
    address TEXT NOT NULL,
    label TEXT,
    is_central BOOLEAN NOT NULL DEFAULT FALSE
);

-- Создание схемы sales
CREATE SCHEMA IF NOT EXISTS sales AUTHORIZATION app_user;

CREATE TABLE IF NOT EXISTS sales.orders (
    id SERIAL PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'unpublished',
    total_amount DECIMAL(10, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    warehouse_id INTEGER NOT NULL,
    CONSTRAINT orders_status_check CHECK (status IN ('unpublished', 'new', 'processing', 'pending', 'packing', 'shipped')),
    CONSTRAINT fk_orders_warehouse_id FOREIGN KEY (warehouse_id) REFERENCES catalog.warehouses(id)
);

CREATE TABLE IF NOT EXISTS sales.order_items (
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
    CONSTRAINT pk_order_items PRIMARY KEY (order_id, product_id),
    CONSTRAINT fk_order_items_order_id FOREIGN KEY (order_id) REFERENCES sales.orders(id) ON DELETE CASCADE,
    CONSTRAINT fk_order_items_product_id FOREIGN KEY (product_id) REFERENCES catalog.products(id)
);