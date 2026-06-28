-- Добавляем поле processing_by
ALTER TABLE sales.orders ADD COLUMN processing_by INTEGER;
ALTER TABLE sales.orders ADD CONSTRAINT fk_orders_processing_by
    FOREIGN KEY (processing_by) REFERENCES auth.users(id);