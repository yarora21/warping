"""Database boundary for loading, reconciling, and reading assignment results."""
import json
from contextlib import contextmanager
from uuid import uuid4
from sqlalchemy import text
from app.database import engine
from app.resolver import Inputs, Interval, resolve_timeline

LOCK_ID = 72021001


def load_inputs(connection) -> Inputs:
    def rows(table, versioned=True):
        clause = ' WHERE superseded_at IS NULL' if versioned else ''
        return [dict(r) for r in connection.execute(text(f'SELECT * FROM {table}{clause} ORDER BY id')).mappings()]
    policies = [dict(r) for r in connection.execute(text('''
        SELECT v.*, p.category_id FROM policy_versions v JOIN policies p ON p.id=v.policy_id
        WHERE v.superseded_at IS NULL ORDER BY v.id
    ''')).mappings()]
    return Inputs(employees=rows('employees', False), jobs=rows('employment_versions'),
                  attributes=rows('employee_versions'), memberships=rows('group_memberships'),
                  categories=rows('assignment_categories', False), policies=policies,
                  rules=rows('assignment_rule_versions'), overrides=rows('employee_assignment_overrides'))


@contextmanager
def assignment_transaction():
    # READ COMMITTED makes reads after the lock see the previous writer's commit.
    with engine.connect().execution_options(isolation_level='READ COMMITTED') as connection:
        with connection.begin():
            connection.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': LOCK_ID})
            yield connection


def stored_intervals(connection, employee_ids=None) -> list[tuple[str, Interval]]:
    clause = ' WHERE employee_id = ANY(:ids)' if employee_ids is not None else ''
    rows = connection.execute(text('''SELECT id, employee_id, category_id, policy_id, is_single,
        lower(valid_during) AS effective_from, upper(valid_during) AS effective_to, explanation
        FROM employee_assignments''' + clause + ' ORDER BY employee_id, lower(valid_during), category_id, policy_id'),
        {'ids': employee_ids} if employee_ids is not None else {}).mappings()
    return [(str(row['id']), Interval.model_validate({k: v for k, v in row.items() if k != 'id'})) for row in rows]


def reconcile(connection, employee_ids=None, reason='Recalculate assignments') -> int:
    """Caller holds the company lock, including any input edits before this call."""
    inputs = load_inputs(connection)
    ids = sorted(set(employee_ids if employee_ids is not None else [e['id'] for e in inputs.employees]))
    desired = []
    for employee_id in ids:
        intervals, gaps = resolve_timeline(inputs, employee_id)
        if gaps:
            raise ValueError(gaps[0].message + f' Employee: {employee_id}')
        desired.extend(intervals)
    old = {interval.model_dump_json(): (row_id, interval) for row_id, interval in stored_intervals(connection, ids)}
    new = {interval.model_dump_json(): interval for interval in desired}
    removed, added = sorted(old.keys() - new.keys()), sorted(new.keys() - old.keys())
    if not removed and not added:
        return 0
    run_id = str(uuid4())
    connection.execute(text('''INSERT INTO reconciliation_runs (id,actor,reason,employee_ids)
        VALUES (:id,'taylor',:reason,CAST(:employees AS jsonb))'''),
        {'id': run_id, 'reason': reason, 'employees': json.dumps(ids)})
    for key in removed:
        connection.execute(text('DELETE FROM employee_assignments WHERE id=:id'), {'id': old[key][0]})
    for key in added:
        interval = new[key]
        connection.execute(text('''INSERT INTO employee_assignments
            (id,employee_id,category_id,policy_id,is_single,valid_during,explanation)
            VALUES (:id,:employee,:category,:policy,:single,daterange(:start,:end,'[)'),CAST(:explanation AS jsonb))'''),
            {'id': str(uuid4()), 'employee': interval.employee_id, 'category': interval.category_id,
             'policy': interval.policy_id, 'single': interval.is_single, 'start': interval.effective_from,
             'end': interval.effective_to, 'explanation': interval.explanation.model_dump_json()})
    for action, keys in (('removed', removed), ('assigned', added)):
        for key in keys:
            connection.execute(text('''INSERT INTO assignment_changes (run_id,action,snapshot)
                VALUES (:run,:action,CAST(:snapshot AS jsonb))'''), {'run': run_id, 'action': action, 'snapshot': key})
    return len(removed) + len(added)


if __name__ == '__main__':
    with assignment_transaction() as connection:
        count = reconcile(connection)
    print(f'{count} assignment interval changes.')
