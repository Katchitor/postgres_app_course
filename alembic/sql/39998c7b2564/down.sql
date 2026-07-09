-- 1. Отзываем права на представление
REVOKE SELECT ON inventory.orders_for_worker FROM worker;

-- 2. Удаляем представление
DROP VIEW IF EXISTS inventory.orders_for_worker;

-- 3. Удаляем внешний ключ
ALTER TABLE auth.users DROP CONSTRAINT IF EXISTS fk_users_warehouse_id;

-- 4. Удаляем поле warehouse_id
ALTER TABLE auth.users DROP COLUMN IF EXISTS warehouse_id;