-- Create analytics database for data warehouse
CREATE DATABASE analytics_db;

-- Grant access to airflow user (Postgres container default user)
-- Both airflow (metadata) and analytics_db (warehouse) run on same Postgres instance
