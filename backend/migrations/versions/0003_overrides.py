"""Employment-scoped manual assignment revisions."""
from alembic import op

revision = '0003'
down_revision = '0002'


def upgrade():
    op.execute('''
        CREATE TABLE employee_assignment_overrides (
            id text PRIMARY KEY,
            employment_id text NOT NULL REFERENCES employments(id),
            category_id text NOT NULL,
            policy_id text,
            is_single boolean NOT NULL,
            action text NOT NULL CHECK (action IN ('set','add','exclude','clear')),
            effective_from date NOT NULL,
            effective_to date,
            created_at timestamptz NOT NULL DEFAULT now(),
            created_by text NOT NULL,
            reason text NOT NULL CHECK (length(trim(reason)) > 0),
            superseded_at timestamptz,
            superseded_by text,
            superseded_reason text,
            FOREIGN KEY (category_id,is_single) REFERENCES assignment_categories(id,is_single),
            FOREIGN KEY (policy_id,category_id) REFERENCES policies(id,category_id),
            CHECK ((action='clear' AND policy_id IS NULL) OR (action<>'clear' AND policy_id IS NOT NULL)),
            CHECK ((is_single AND action IN ('set','clear')) OR (NOT is_single AND action IN ('add','exclude'))),
            CHECK (effective_to IS NULL OR effective_to>effective_from),
            CHECK ((superseded_at IS NULL AND superseded_by IS NULL AND superseded_reason IS NULL)
                OR (superseded_at IS NOT NULL AND superseded_by IS NOT NULL AND superseded_reason IS NOT NULL)),
            EXCLUDE USING gist (employment_id WITH =,category_id WITH =,daterange(effective_from,effective_to,'[)') WITH &&)
                WHERE (superseded_at IS NULL AND is_single),
            EXCLUDE USING gist (employment_id WITH =,policy_id WITH =,daterange(effective_from,effective_to,'[)') WITH &&)
                WHERE (superseded_at IS NULL AND NOT is_single)
        );
        CREATE TRIGGER preserve_revision BEFORE UPDATE OR DELETE ON employee_assignment_overrides
            FOR EACH ROW EXECUTE FUNCTION preserve_revision();
    ''')


def downgrade():
    op.execute('DROP TABLE employee_assignment_overrides')
