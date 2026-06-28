-- Удаляем внешний ключ
ALTER TABLE sales.orders DROP CONSTRAINT IF EXISTS fk_orders_processing_by;

-- Удаляем поле processing_by
ALTER TABLE sales.orders DROP COLUMN IF EXISTS processing_by;