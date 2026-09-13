from datetime import date
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.database import engine
from app.assignments import LOCK_ID, load_inputs, reconcile, stored_intervals
from app.resolver import active, resolve
from app.seed import seed


def test_stored_results_match_point_resolution_and_reruns_do_not_write():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            seed(connection)
            assert reconcile(connection) == 0
            original = stored_intervals(connection)
            source = load_inputs(connection)
            for day in (date(2026,9,12),date(2026,9,30),date(2026,10,1),date(2099,1,1)):
                expected = resolve(source,[e['id'] for e in source.employees],day).assignments
                actual = [interval for _,interval in original if active(interval.model_dump(),day)]
                key = lambda a: (a.employee_id,a.category_id,a.policy_id)
                assert [(key(a),a.explanation) for a in sorted(actual,key=key)] == [(key(a),a.explanation) for a in sorted(expected,key=key)]
            seed(connection)
            assert stored_intervals(connection) == original
            # A category/policy mismatch and overlapping assignments are both rejected.
            for sql in (
                """INSERT INTO employee_assignments SELECT :id,employee_id,category_id,policy_id,is_single,valid_during,explanation FROM employee_assignments LIMIT 1""",
                """INSERT INTO employee_assignments SELECT :id,employee_id,'pay','github',true,valid_during,explanation FROM employee_assignments LIMIT 1""",
            ):
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(text(sql),{'id':str(uuid4())})
        finally:
            transaction.rollback()


def test_failed_reconciliation_rolls_back_input_and_outcomes():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            seed(connection)
            original = stored_intervals(connection)
            with pytest.raises(ValueError):
                with connection.begin_nested():
                    connection.execute(text("""UPDATE assignment_rule_versions SET superseded_at=now(),superseded_by='test',superseded_reason='Remove defaults'
                        WHERE policy_id IN ('monthly','biweekly') AND superseded_at IS NULL"""))
                    reconcile(connection)
            assert stored_intervals(connection) == original
            assert connection.execute(text("SELECT count(*) FROM assignment_rule_versions WHERE policy_id='monthly' AND superseded_at IS NULL")).scalar() == 1
        finally:
            transaction.rollback()


def test_membership_removal_reconciles_and_keeps_old_evidence():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            seed(connection)
            assert any(i.policy_id == 'figma' for _,i in stored_intervals(connection,['jamie']))
            connection.execute(text("""UPDATE group_memberships SET superseded_at=now(),superseded_by='test',
                superseded_reason='Remove test membership' WHERE employment_id='job_jamie' AND superseded_at IS NULL"""))
            assert reconcile(connection,['jamie']) > 0
            assert not any(i.policy_id == 'figma' for _,i in stored_intervals(connection,['jamie']))
            assert connection.execute(text("""SELECT count(*) FROM assignment_changes WHERE action='removed'
                AND snapshot->>'employee_id'='jamie' AND snapshot->>'policy_id'='figma'""")).scalar() > 0
            assert reconcile(connection,['jamie']) == 0
        finally:
            transaction.rollback()


def test_company_lock_orders_writers_and_next_snapshot_sees_commit():
    # Two explicitly ordered connections, no sleeps or thread races. The marker is
    # a test-owned employee identity and is removed after the committed-read check.
    marker = 'test_lock_' + uuid4().hex
    with engine.connect() as first, engine.connect() as second:
        try:
            first.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key':LOCK_ID})
            first.execute(text('INSERT INTO employees VALUES (:id,:id,:email)'),{'id':marker,'email':marker+'@example.test'})
            assert second.execute(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':LOCK_ID}).scalar() is False
            assert second.execute(text('SELECT count(*) FROM employees WHERE id=:id'),{'id':marker}).scalar() == 0
            first.commit()
            second.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':LOCK_ID})
            assert marker in {e['id'] for e in load_inputs(second).employees}
            second.rollback()
        finally:
            first.rollback()
            second.rollback()
            first.execute(text('DELETE FROM employees WHERE id=:id'),{'id':marker})
            first.commit()
