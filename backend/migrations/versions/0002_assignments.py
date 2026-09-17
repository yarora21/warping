"""Rules and complete, explainable assignment timelines."""
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.execute("""
        CREATE TABLE assignment_rules (id text PRIMARY KEY);
        CREATE TABLE assignment_rule_versions (
            id text PRIMARY KEY,
            rule_id text NOT NULL REFERENCES assignment_rules(id),
            policy_id text NOT NULL REFERENCES policies(id),
            name text NOT NULL,
            priority integer NOT NULL CHECK (priority >= 0),
            conditions jsonb NOT NULL,
            effective_from date NOT NULL,
            effective_to date,
            created_at timestamptz NOT NULL DEFAULT now(),
            created_by text NOT NULL,
            change_reason text NOT NULL,
            superseded_at timestamptz,
            superseded_by text,
            superseded_reason text,
            CHECK (effective_to IS NULL OR effective_to > effective_from),
            CHECK ((superseded_at IS NULL AND superseded_by IS NULL AND superseded_reason IS NULL)
                OR (superseded_at IS NOT NULL AND superseded_by IS NOT NULL AND superseded_reason IS NOT NULL)),
            EXCLUDE USING gist (rule_id WITH =, daterange(effective_from,effective_to,'[)') WITH &&)
                WHERE (superseded_at IS NULL)
        );
        CREATE TRIGGER preserve_revision BEFORE UPDATE OR DELETE ON assignment_rule_versions
            FOR EACH ROW EXECUTE FUNCTION preserve_revision();
        ALTER TABLE assignment_categories ADD COLUMN is_single boolean GENERATED ALWAYS AS (cardinality <> 'many') STORED;
        ALTER TABLE assignment_categories ADD UNIQUE (id, is_single);
        ALTER TABLE policies ADD UNIQUE (id, category_id);
        CREATE TABLE reconciliation_runs (
            id uuid PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now(),
            actor text NOT NULL,
            reason text NOT NULL,
            employee_ids jsonb NOT NULL
        );
        CREATE TABLE employee_assignments (
            id uuid PRIMARY KEY,
            employee_id text NOT NULL REFERENCES employees(id),
            category_id text NOT NULL,
            policy_id text NOT NULL,
            is_single boolean NOT NULL,
            valid_during daterange NOT NULL,
            explanation jsonb NOT NULL,
            FOREIGN KEY (category_id,is_single) REFERENCES assignment_categories(id,is_single),
            FOREIGN KEY (policy_id,category_id) REFERENCES policies(id,category_id),
            CHECK (NOT isempty(valid_during) AND NOT lower_inf(valid_during)),
            EXCLUDE USING gist (employee_id WITH =,category_id WITH =,valid_during WITH &&) WHERE (is_single),
            EXCLUDE USING gist (employee_id WITH =,policy_id WITH =,valid_during WITH &&)
        );
        CREATE TABLE assignment_changes (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES reconciliation_runs(id),
            action text NOT NULL CHECK (action IN ('assigned','removed')),
            snapshot jsonb NOT NULL
        );
    """)


def downgrade():
    for table in ('assignment_changes', 'employee_assignments', 'reconciliation_runs',
                  'assignment_rule_versions', 'assignment_rules'):
        op.execute(f'DROP TABLE {table}')
    op.execute('ALTER TABLE policies DROP CONSTRAINT policies_id_category_id_key')
    op.execute('ALTER TABLE assignment_categories DROP COLUMN is_single')
