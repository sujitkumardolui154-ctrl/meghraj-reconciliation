"""R20 disposable PostgreSQL integration and rollback/conservation QA.

This is NOT a database migration or live application finance integration.
It refuses remote hosts and any database other than 'sbi_r20_synthetic_qa'.
Synthetic ledger tables live only in a disposable GitHub Actions PostgreSQL
service. All staged reservations are explicitly rolled back, and schema dropped.
"""
from __future__ import annotations
from decimal import Decimal

DBNAME = "sbi_r20_synthetic_qa"
SCHEMA = "sbi_r20_shadow_only"


class PostgreSQLIsolationRefusal(ValueError):
    pass


def _require_disposable_dsn(dsn):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    data = conninfo_to_dict(dsn)
    if (data.get("dbname") != DBNAME
            or data.get("host") not in ("127.0.0.1", "localhost")
            or data.get("port", "5432") != "5432"):
        raise PostgreSQLIsolationRefusal("NON_DISPOSABLE_POSTGRESQL_TARGET_REFUSED")
    return data


SCHEMA_SQL = """
CREATE SCHEMA sbi_r20_shadow_only;
CREATE TABLE sbi_r20_shadow_only.payment (
    payment_key text PRIMARY KEY CHECK(payment_key ~ '^SYN-PAY-[0-9]{3,6}$'),
    sol text NOT NULL CHECK(sol ~ '^[0-9]{1,12}$'),
    client text NOT NULL CHECK(client LIKE 'SYNTHETIC %'),
    credit numeric(18,2) NOT NULL CHECK(credit > 0)
);
CREATE TABLE sbi_r20_shadow_only.invoice (
    invoice_key text PRIMARY KEY CHECK(invoice_key ~ '^SYN-MXP-[0-9]{3,6}$'),
    sol text NOT NULL CHECK(sol ~ '^[0-9]{1,12}$'),
    client text NOT NULL CHECK(client LIKE 'SYNTHETIC %'),
    outstanding numeric(18,2) NOT NULL CHECK(outstanding >= 0),
    protected_s_nonblank boolean NOT NULL
);
CREATE TABLE sbi_r20_shadow_only.reservation (
    payment_key text NOT NULL REFERENCES sbi_r20_shadow_only.payment,
    invoice_key text NOT NULL REFERENCES sbi_r20_shadow_only.invoice,
    amount numeric(18,2) NOT NULL CHECK(amount > 0),
    PRIMARY KEY(payment_key,invoice_key)
);
CREATE FUNCTION sbi_r20_shadow_only.enforce_shadow_conservation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    p sbi_r20_shadow_only.payment%ROWTYPE;
    i sbi_r20_shadow_only.invoice%ROWTYPE;
    bank_alloc numeric(18,2);
    invoice_alloc numeric(18,2);
BEGIN
    SELECT * INTO p FROM sbi_r20_shadow_only.payment
      WHERE payment_key=NEW.payment_key FOR UPDATE;
    SELECT * INTO i FROM sbi_r20_shadow_only.invoice
      WHERE invoice_key=NEW.invoice_key FOR UPDATE;
    IF p.payment_key IS NULL OR i.invoice_key IS NULL THEN
       RAISE EXCEPTION 'UNKNOWN_SOURCE' USING ERRCODE='23514';
    END IF;
    IF p.sol<>i.sol OR p.client<>i.client OR i.protected_s_nonblank THEN
       RAISE EXCEPTION 'SOURCE_IDENTITY_OR_MARKER_HOLD' USING ERRCODE='23514';
    END IF;
    SELECT COALESCE(SUM(amount),0) INTO bank_alloc
      FROM sbi_r20_shadow_only.reservation
      WHERE payment_key=NEW.payment_key;
    SELECT COALESCE(SUM(amount),0) INTO invoice_alloc
      FROM sbi_r20_shadow_only.reservation
      WHERE invoice_key=NEW.invoice_key;
    IF bank_alloc + NEW.amount > p.credit
       OR invoice_alloc + NEW.amount > i.outstanding THEN
       RAISE EXCEPTION 'RESERVATION_EXCEEDS_SOURCE_CAPACITY'
         USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER enforce_shadow_reservation
BEFORE INSERT ON sbi_r20_shadow_only.reservation
FOR EACH ROW EXECUTE FUNCTION sbi_r20_shadow_only.enforce_shadow_conservation();
INSERT INTO sbi_r20_shadow_only.payment VALUES
  ('SYN-PAY-001','0001','SYNTHETIC ALPHA',1160.00),
  ('SYN-PAY-002','0001','SYNTHETIC ALPHA',400.00),
  ('SYN-PAY-003','0002','SYNTHETIC BETA',300.00);
INSERT INTO sbi_r20_shadow_only.invoice VALUES
  ('SYN-MXP-001','0001','SYNTHETIC ALPHA',1180.00,false),
  ('SYN-MXP-002','0001','SYNTHETIC ALPHA',600.00,false),
  ('SYN-MXP-003','0001','SYNTHETIC ALPHA',200.00,true),
  ('SYN-MXP-004','0002','SYNTHETIC BETA',350.00,false);
"""


class ForcedRollback(Exception):
    pass


def run_ephemeral_pg_probe(dsn):
    import psycopg
    from psycopg import errors
    _require_disposable_dsn(dsn)
    result = {
        "stage": "R20_EPHEMERAL_POSTGRESQL_ONLY",
        "real_financial_database_connected": False,
        "production_database_mutations": 0,
        "fin_apply_locked": True,
        "postgresql_schema_created_in_disposable_ci_only": False,
        "readonly_transaction_write_denied": False,
        "readonly_role_write_denied": False,
        "duplicate_reservation_rejected": False,
        "credit_capacity_violation_rejected": False,
        "invoice_capacity_violation_rejected": False,
        "protected_invoice_rejected": False,
        "cross_sol_rejected": False,
        "rolled_back_all_synthetic_reservations": False,
        "disposable_schema_dropped": False,
    }
    with psycopg.connect(dsn, autocommit=True) as con:
        with con.cursor() as cur:
            cur.execute("SELECT current_database(), inet_server_addr()")
            database, server_address = cur.fetchone()
            if database != DBNAME or str(server_address) not in ("127.0.0.1", "::1"):
                raise PostgreSQLIsolationRefusal("NOT_LOCAL_DISPOSABLE_DATABASE")
            try:
                cur.execute(SCHEMA_SQL)
                result["postgresql_schema_created_in_disposable_ci_only"] = True
                cur.execute("SELECT COUNT(*) FROM sbi_r20_shadow_only.payment")
                assert cur.fetchone()[0] == 3
                cur.execute("SELECT COUNT(*) FROM sbi_r20_shadow_only.invoice")
                assert cur.fetchone()[0] == 4

                try:
                    with con.transaction():
                        cur.execute("SET TRANSACTION READ ONLY")
                        cur.execute(
                            "INSERT INTO sbi_r20_shadow_only.reservation VALUES "
                            "('SYN-PAY-001','SYN-MXP-001',1)"
                        )
                except errors.ReadOnlySqlTransaction:
                    result["readonly_transaction_write_denied"] = True

                # Staging scratch role inherits only SELECT on synthetic tables.
                cur.execute("CREATE ROLE sbi_r20_shadow_readonly NOLOGIN")
                try:
                    cur.execute("GRANT USAGE ON SCHEMA sbi_r20_shadow_only TO sbi_r20_shadow_readonly")
                    cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA sbi_r20_shadow_only TO sbi_r20_shadow_readonly")
                    cur.execute("SET ROLE sbi_r20_shadow_readonly")
                    try:
                        with con.transaction():
                            cur.execute("SELECT count(*) FROM sbi_r20_shadow_only.payment")
                            assert cur.fetchone()[0] == 3
                            cur.execute(
                                "INSERT INTO sbi_r20_shadow_only.reservation VALUES "
                                "('SYN-PAY-001','SYN-MXP-001',1)"
                            )
                    except errors.InsufficientPrivilege:
                        result["readonly_role_write_denied"] = True
                finally:
                    cur.execute("RESET ROLE")
                    cur.execute("DROP ROLE IF EXISTS sbi_r20_shadow_readonly")

                try:
                    with con.transaction():
                        # Valid two-edge assignment (100 + 200) is not a posting.
                        cur.execute(
                            "INSERT INTO sbi_r20_shadow_only.reservation VALUES "
                            "('SYN-PAY-001','SYN-MXP-001',100)"
                        )
                        cur.execute(
                            "INSERT INTO sbi_r20_shadow_only.reservation VALUES "
                            "('SYN-PAY-001','SYN-MXP-002',200)"
                        )
                        cases = [
                            ("duplicate_reservation_rejected",
                             "('SYN-PAY-001','SYN-MXP-001',1)",
                             errors.UniqueViolation),
                            ("credit_capacity_violation_rejected",
                             "('SYN-PAY-001','SYN-MXP-002',1000)",
                             errors.UniqueViolation),
                            ("invoice_capacity_violation_rejected",
                             "('SYN-PAY-002','SYN-MXP-001',1100)",
                             errors.CheckViolation),
                            ("protected_invoice_rejected",
                             "('SYN-PAY-002','SYN-MXP-003',1)",
                             errors.CheckViolation),
                            ("cross_sol_rejected",
                             "('SYN-PAY-003','SYN-MXP-002',1)",
                             errors.CheckViolation),
                        ]
                        for key, row_values, expected_error in cases:
                            try:
                                with con.transaction():
                                    cur.execute(
                                        "INSERT INTO sbi_r20_shadow_only.reservation VALUES "
                                        + row_values
                                    )
                            except expected_error:
                                result[key] = True
                        raise ForcedRollback()
                except ForcedRollback:
                    pass
                cur.execute("SELECT COUNT(*) FROM sbi_r20_shadow_only.reservation")
                result["rolled_back_all_synthetic_reservations"] = cur.fetchone()[0] == 0
            finally:
                cur.execute("RESET ROLE")
                cur.execute("DROP SCHEMA IF EXISTS sbi_r20_shadow_only CASCADE")
                # Scratch environment only, no production database names.
                result["disposable_schema_dropped"] = True
    return result
