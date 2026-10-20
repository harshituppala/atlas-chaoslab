-- Reviewed provisioning reference, not automatically executed or deployed.
-- Prerequisites: dedicated database, migrated schema "atlas", privileged operator.
-- LOGIN roles have no password until an operator configures managed secrets/TLS.
-- Run once; never reuse the database owner or grant role membership between services.
CREATE ROLE atlas_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE atlas_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;
GRANT USAGE ON SCHEMA atlas TO atlas_api, atlas_worker;
GRANT SELECT ON atlas.alembic_version TO atlas_api, atlas_worker;
GRANT SELECT, INSERT ON atlas.runs TO atlas_api, atlas_worker;
GRANT SELECT, INSERT ON atlas.reviews TO atlas_api, atlas_worker;
GRANT UPDATE ON atlas.reviews TO atlas_api;
GRANT SELECT, INSERT ON atlas.audit TO atlas_api, atlas_worker;
GRANT SELECT, INSERT, UPDATE ON atlas.jobs TO atlas_api;
GRANT SELECT, UPDATE ON atlas.jobs TO atlas_worker;
GRANT SELECT, INSERT ON atlas.documents TO atlas_api;
GRANT SELECT ON atlas.documents TO atlas_worker;
GRANT SELECT, INSERT, UPDATE ON atlas.document_quotas TO atlas_api;
GRANT SELECT, INSERT ON atlas.retrieval_corpora, atlas.retrieval_chunks TO atlas_api, atlas_worker;
GRANT SELECT ON atlas.memberships TO atlas_api;
-- No membership writes, audit updates, DELETE, TRUNCATE, DDL or table ownership.
-- No default privileges: every new table requires a reviewed grant/migration.
