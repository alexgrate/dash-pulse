-- Mirrors production schema/table/column names.
-- Collations are deliberately mixed like production (cba-mcs = unicode_ci, mcs = 0900_ai_ci)
-- so collation bugs show up locally, not in prod.

CREATE DATABASE IF NOT EXISTS `dashmfb-mcs`          CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS `dashmfb-cba-mcs`      CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `dashmfb-billspayment` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `dashmfb-notification` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `dashmfb-authservice`  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- ─── dashmfb-mcs (stores Lagos time) ───────────────────────────────
CREATE TABLE `dashmfb-mcs`.DashMFB_Transactions (
  ID BIGINT AUTO_INCREMENT PRIMARY KEY,
  PAYMENT_REFERENCE VARCHAR(100) UNIQUE,
  TRANSACTION_TYPE VARCHAR(50),
  AMOUNT DECIMAL(19,2),
  CREATED DATETIME,
  UPDATED DATETIME,
  CBA_RESPONSE_CODE VARCHAR(10),
  CBA_MESSAGE LONGTEXT,
  PROVIDER VARCHAR(50),
  ACCOUNT_NUMBER VARCHAR(20),
  BENEFICIARY_BANK_NAME VARCHAR(100),
  LOCATION_LAT VARCHAR(30),
  LOCATION_LON VARCHAR(30),
  TENANT_ID VARCHAR(50),
  INDEX (ACCOUNT_NUMBER)
);

CREATE TABLE `dashmfb-mcs`.UM_LOGIN_TRAIL (
  ID BIGINT AUTO_INCREMENT PRIMARY KEY,
  DEVICE_ID VARCHAR(100),
  USERNAME VARCHAR(100),
  LOCATION VARCHAR(255),
  DEVICE_OS VARCHAR(20),
  LOGIN_TIME DATETIME,
  TENANT_ID VARCHAR(50),
  INDEX (USERNAME),
  INDEX (TENANT_ID)
);

CREATE TABLE `dashmfb-mcs`.DashMFB_UM_ONBOARDING_PROCESS (
  ID BIGINT AUTO_INCREMENT PRIMARY KEY,
  ONBOARDING_PHASE VARCHAR(50),
  NEXT_ONBOARDING_PHASE VARCHAR(50),
  DATE_CREATED DATETIME,
  DATE_UPDATED DATETIME,
  ACCOUNT_OPENED_DATE DATETIME,
  TENANT_ID VARCHAR(50)
);

CREATE TABLE `dashmfb-mcs`.LIVENESS_CHECK_LOG (
  ID BIGINT AUTO_INCREMENT PRIMARY KEY,
  DATE_CREATED DATETIME,
  SCORE DECIMAL(10,4),
  CHANNEL VARCHAR(20),
  STATUS VARCHAR(20),
  PURPOSE VARCHAR(30),
  USERNAME VARCHAR(100),
  TENANT_ID VARCHAR(50),
  INDEX (USERNAME)
);

-- ─── dashmfb-cba-mcs (stores UTC) ──────────────────────────────────
CREATE TABLE `dashmfb-cba-mcs`.payment_transactions (
  id VARCHAR(36) PRIMARY KEY,
  transfer_amount DECIMAL(19,2),
  beneficiary_bank_name VARCHAR(100),
  source_account VARCHAR(20),
  payment_reference VARCHAR(100) UNIQUE,
  provider VARCHAR(30),
  status VARCHAR(20),
  transfer_type VARCHAR(10),
  transaction_direction VARCHAR(20),
  transaction_category VARCHAR(30),
  requery_count INT DEFAULT 0,
  created_at DATETIME,
  updated_at DATETIME,
  INDEX (source_account),
  INDEX (status),
  INDEX (created_at)
);

CREATE TABLE `dashmfb-cba-mcs`.quest_enrollments (
  id VARCHAR(36) PRIMARY KEY,
  customer_id VARCHAR(50) UNIQUE,
  status VARCHAR(20),
  total_earned DECIMAL(19,2),
  enrolled_at DATETIME,
  created_at DATETIME,
  INDEX (status)
);

CREATE TABLE `dashmfb-cba-mcs`.quest_reward_transactions (
  id VARCHAR(36) PRIMARY KEY,
  enrollment_id VARCHAR(36),
  reward_type VARCHAR(30),
  amount DECIMAL(19,2),
  status VARCHAR(20),
  created_at DATETIME,
  INDEX (enrollment_id),
  INDEX (status)
);

-- ─── dashmfb-billspayment (stores UTC) ─────────────────────────────
CREATE TABLE `dashmfb-billspayment`.biller_categories (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100),
  created_at DATETIME
);

CREATE TABLE `dashmfb-billspayment`.billers (
  id VARCHAR(50) PRIMARY KEY,
  code VARCHAR(50) UNIQUE,
  name VARCHAR(100),
  category_id BIGINT,
  created_at DATETIME,
  INDEX (category_id)
);

CREATE TABLE `dashmfb-billspayment`.bills_payment_transactions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  amount DECIMAL(19,2),
  biller_id VARCHAR(50),
  request_reference VARCHAR(100) UNIQUE,
  status VARCHAR(20),
  response_code VARCHAR(10),
  response_message VARCHAR(255),
  latitude VARCHAR(30),
  longitude VARCHAR(30),
  created_at DATETIME(3),
  completed_at DATETIME(3)
);

-- ─── dashmfb-notification (TIMESTAMP, returned in session tz) ──────
CREATE TABLE `dashmfb-notification`.notifications (
  id VARCHAR(36) PRIMARY KEY,
  notification_channel VARCHAR(10),
  status VARCHAR(20),
  created_at TIMESTAMP NULL
);

-- ─── dashmfb-authservice (stores Lagos time) ───────────────────────
CREATE TABLE `dashmfb-authservice`.UM_FLAMINGO_USER (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) UNIQUE,
  registration_date DATETIME(6),
  account_closure_status ENUM('NONE','PENDING','CLOSED'),
  created_at DATETIME
);

CREATE TABLE `dashmfb-authservice`.ResetToken (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  tokenType TINYINT,
  generatedOn DATETIME,
  usedOn DATETIME,
  created_at DATETIME
);
