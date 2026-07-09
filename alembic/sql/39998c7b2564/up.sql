-- Добавляем поле warehouse_id в таблицу users
ALTER TABLE auth.users ADD COLUMN warehouse_id INTEGER;
ALTER TABLE auth.users ADD CONSTRAINT fk_users_warehouse_id
    FOREIGN KEY (warehouse_id) REFERENCES catalog.warehouses(id) ON DELETE SET NULL;

-- Создаем представление в схеме inventory для worker'ов
CREATE VIEW inventory.orders_for_worker AS
SELECT
    o.id,
    o.status,
    o.warehouse_id,
    o.created_at
FROM sales.orders o
WHERE o.status IN ('packing', 'shipped');

-- Даем права на представление worker'у
GRANT SELECT ON inventory.orders_for_worker TO worker;