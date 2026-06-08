-- RestockRadar — MySQL schema
-- Multi-source new-product monitor. Designed for fast "is this new?" checks
-- and for serving the most-recent finds to a mobile app with low latency.

CREATE DATABASE IF NOT EXISTS restockradar
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE restockradar;

-- One row per configured source site. The admin UI edits these.
CREATE TABLE sources (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
  slug            VARCHAR(60)  NOT NULL,
  display_name    VARCHAR(120) NOT NULL,
  base_url        VARCHAR(255) NOT NULL,
  enabled         TINYINT(1)   NOT NULL DEFAULT 1,
  poll_interval_s INT UNSIGNED NOT NULL DEFAULT 300,
  last_run_at     DATETIME     NULL,
  last_status     ENUM('ok','degraded','error','never') NOT NULL DEFAULT 'never',
  last_error      VARCHAR(255) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_sources_slug (slug)
) ENGINE=InnoDB;

-- One row per product seen. dedup_key makes "have we seen this?" a single
-- indexed lookup, and lets the scraper INSERT ... ON DUPLICATE KEY UPDATE.
CREATE TABLE products (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_id    INT UNSIGNED    NOT NULL,
  dedup_key    VARCHAR(190)    NOT NULL,         -- "{source_slug}:{external_id}"
  external_id  VARCHAR(120)    NOT NULL,
  title        VARCHAR(255)    NOT NULL,
  price        DECIMAL(10,2)   NULL,
  currency     CHAR(3)         NOT NULL DEFAULT 'GBP',
  url          VARCHAR(512)    NOT NULL,
  image_url    VARCHAR(512)    NULL,
  in_stock     TINYINT(1)      NOT NULL DEFAULT 1,
  first_seen   DATETIME        NOT NULL,         -- when WE first detected it
  last_seen    DATETIME        NOT NULL,
  notified     TINYINT(1)      NOT NULL DEFAULT 0, -- pushed to the app yet?
  PRIMARY KEY (id),
  UNIQUE KEY uq_products_dedup (dedup_key),
  KEY idx_products_first_seen (first_seen),       -- "newest first" feed
  KEY idx_products_source (source_id),
  KEY idx_products_unnotified (notified, first_seen),
  CONSTRAINT fk_products_source FOREIGN KEY (source_id)
    REFERENCES sources (id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Lightweight per-run telemetry so the admin can show source health and the
-- "detection lag" KPI without scanning the whole products table.
CREATE TABLE scrape_runs (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_id    INT UNSIGNED    NOT NULL,
  started_at   DATETIME        NOT NULL,
  duration_ms  INT UNSIGNED    NULL,
  items_found  INT UNSIGNED    NOT NULL DEFAULT 0,
  items_new    INT UNSIGNED    NOT NULL DEFAULT 0,
  status       ENUM('ok','degraded','error') NOT NULL,
  note         VARCHAR(255)    NULL,
  PRIMARY KEY (id),
  KEY idx_runs_source_time (source_id, started_at)
) ENGINE=InnoDB;
