"""Directory/catalog foundation. Explicit SQL keeps temporal constraints reviewable."""
from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("""
        CREATE TABLE employees (
            id text PRIMARY KEY,
            name text NOT NULL,
            email text NOT NULL UNIQUE
        );
        CREATE TABLE departments (id text PRIMARY KEY, name text NOT NULL UNIQUE);
        CREATE TABLE groups (id text PRIMARY KEY, name text NOT NULL UNIQUE);
        CREATE TABLE employments (
            id text PRIMARY KEY,
            employee_id text NOT NULL REFERENCES employees(id),
            UNIQUE (id, employee_id)
        );
        CREATE TABLE assignment_categories (
            id text PRIMARY KEY,
            name text NOT NULL,
            cardinality text NOT NULL CHECK (cardinality IN ('exactly_one', 'at_most_one', 'many'))
        );
        CREATE TABLE policies (
            id text PRIMARY KEY,
            category_id text NOT NULL REFERENCES assignment_categories(id)
        );
    """)
    # Only safe constant identifiers below; the repetition is migration-local.
    specs = [
        ("employment_versions", """
            employment_id text NOT NULL,
            employee_id text NOT NULL,
            FOREIGN KEY (employment_id, employee_id) REFERENCES employments(id, employee_id),
        """, "employee_id WITH ="),
        ("employee_versions", """
            employment_id text NOT NULL REFERENCES employments(id),
            employment_type text NOT NULL CHECK (employment_type IN ('salaried', 'hourly', 'contractor')),
            country text NOT NULL,
            state text,
            department_id text NOT NULL REFERENCES departments(id),
            manager_id text REFERENCES employees(id),
        """, "employment_id WITH ="),
        ("group_memberships", """
            employment_id text NOT NULL REFERENCES employments(id),
            group_id text NOT NULL REFERENCES groups(id),
        """, "employment_id WITH =, group_id WITH ="),
        ("policy_versions", """
            policy_id text NOT NULL REFERENCES policies(id),
            name text NOT NULL,
            description text NOT NULL,
        """, "policy_id WITH ="),
    ]
    for table, fields, scope in specs:
        op.execute(f"""
            CREATE TABLE {table} (
                id text PRIMARY KEY,
                {fields}
                effective_from date NOT NULL,
                effective_to date,
                created_at timestamptz NOT NULL DEFAULT now(),
                created_by text NOT NULL,
                change_reason text NOT NULL CHECK (length(trim(change_reason)) > 0),
                superseded_at timestamptz,
                superseded_by text,
                superseded_reason text,
                CHECK (effective_to IS NULL OR effective_to > effective_from),
                CHECK ((superseded_at IS NULL AND superseded_by IS NULL AND superseded_reason IS NULL)
                    OR (superseded_at IS NOT NULL AND superseded_by IS NOT NULL AND superseded_reason IS NOT NULL)),
                EXCLUDE USING gist ({scope}, daterange(effective_from, effective_to, '[)') WITH &&)
                    WHERE (superseded_at IS NULL)
            );
        """)
    op.execute("""
        CREATE FUNCTION preserve_revision() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Recorded revisions cannot be deleted';
            END IF;
            IF OLD.superseded_at IS NOT NULL OR NEW.superseded_at IS NULL
                OR (to_jsonb(NEW) - ARRAY['superseded_at','superseded_by','superseded_reason'])
                    IS DISTINCT FROM
                   (to_jsonb(OLD) - ARRAY['superseded_at','superseded_by','superseded_reason']) THEN
                RAISE EXCEPTION 'Only one-time supersession metadata may change';
            END IF;
            RETURN NEW;
        END $$;
    """)
    for table, _, _ in specs:
        op.execute(f"CREATE TRIGGER preserve_revision BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION preserve_revision()")


def downgrade():
    for table in ("policy_versions", "group_memberships", "employee_versions", "employment_versions",
                  "policies", "assignment_categories", "employments", "groups", "departments", "employees"):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION preserve_revision()")
