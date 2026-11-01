-- SUPERSEDED: DO NOT EXECUTE. Use reviewed freeze-business.sql; broad foreign-owner REVOKE is not source-authorized.
BEGIN;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM service_role;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM service_role;
COMMIT;
