-- writer/schema.sql — journal tables, append-only trigger, cg_writer (insert+select) / cg_reader (select) roles. Idempotent.
-- Role passwords are NOT here: writer/db.py apply_schema() sets them from env with ALTER ROLE.

CREATE TABLE IF NOT EXISTS runs (
    id          text PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       text NOT NULL REFERENCES runs(id),
    txn_id       text NOT NULL,
    invoice_id   text NOT NULL,
    amount       numeric(14,2) NOT NULL CHECK (amount > 0),
    debit_gl     text NOT NULL,
    credit_gl    text NOT NULL,
    narrative    text NOT NULL,
    approved_by  text NOT NULL CHECK (btrim(approved_by) <> ''),
    approved_at  timestamptz NOT NULL,
    row_hash     char(64) NOT NULL,
    UNIQUE (run_id, txn_id, invoice_id)  -- the same line can never be posted twice in a run
);
CREATE INDEX IF NOT EXISTS journal_entries_run_idx ON journal_entries (run_id);

-- Append-only: UPDATE/DELETE/TRUNCATE raise for every role, owner included. Only a superuser
-- who disables triggers (session_replication_role=replica) can tamper, and verify.py catches that.
CREATE OR REPLACE FUNCTION cg_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'journal_entries is append-only (% refused)', TG_OP USING ERRCODE = 'insufficient_privilege';
END $$;
DROP TRIGGER IF EXISTS journal_entries_no_change ON journal_entries;
CREATE TRIGGER journal_entries_no_change BEFORE UPDATE OR DELETE ON journal_entries
    FOR EACH ROW EXECUTE FUNCTION cg_append_only();
DROP TRIGGER IF EXISTS journal_entries_no_truncate ON journal_entries;
CREATE TRIGGER journal_entries_no_truncate BEFORE TRUNCATE ON journal_entries
    FOR EACH STATEMENT EXECUTE FUNCTION cg_append_only();

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cg_writer') THEN CREATE ROLE cg_writer NOLOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cg_reader') THEN CREATE ROLE cg_reader NOLOGIN; END IF;
END $$;

REVOKE ALL ON runs, journal_entries FROM PUBLIC, cg_writer, cg_reader;
GRANT USAGE ON SCHEMA public TO cg_writer, cg_reader;
GRANT SELECT, INSERT ON runs, journal_entries TO cg_writer;
GRANT SELECT ON runs, journal_entries TO cg_reader;
