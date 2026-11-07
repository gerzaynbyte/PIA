CREATE TABLE IF NOT EXISTS orders (
    order_id     VARCHAR(36) PRIMARY KEY,
    customer_id  VARCHAR(36)  NOT NULL,
    status       VARCHAR(40)  NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    created_at   DATETIME(6)  NOT NULL,
    updated_at   DATETIME(6)  NOT NULL,
    is_split     BOOLEAN      NOT NULL DEFAULT FALSE,
    payment_attempts INT      NOT NULL DEFAULT 0,
    warehouse_id VARCHAR(30)  NULL,
    payment_confirmed_at DATETIME(6) NULL,
    delivered_at DATETIME(6)  NULL,
    INDEX idx_customer (customer_id),
    INDEX idx_status (status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS order_items (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id      VARCHAR(36) NOT NULL,
    sku           VARCHAR(30) NOT NULL,
    quantity      INT         NOT NULL,
    unit_price    DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
    UNIQUE KEY uq_order_sku (order_id, sku)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sub_orders (
    folio         VARCHAR(64) PRIMARY KEY,
    order_id      VARCHAR(36) NOT NULL,
    warehouse_id  VARCHAR(30) NOT NULL,
    status        VARCHAR(20) NOT NULL,
    guia_rastreo  VARCHAR(60) NOT NULL DEFAULT '',
    items         JSON        NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE
) ENGINE=InnoDB;
