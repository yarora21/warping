from datetime import date
from uuid import uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.assignments import load_inputs, stored_intervals, reconcile
from app.database import engine
from app.overrides import OverrideCommand, plan_override, save_override
from app.resolver import resolve
from app.seed import seed
from test_resolver import inputs, rule


@pytest.mark.parametrize('action,category,policy,expected', [
    ('set','pay','biweekly',['biweekly']),
    ('clear','pay',None,[]),
    ('add','apps','github',['github']),
    ('exclude','apps','github',[]),
])
def test_override_actions_expire_back_to_rules(action,category,policy,expected):
    data=inputs()
    if action=='clear':
        data.categories[0]['cardinality']='at_most_one'
    if action=='exclude':
        data.rules.append(rule(data,'app',policy='github'))
    data.overrides=[{'id':'o1','employment_id':'job_a','category_id':category,'policy_id':policy,'action':action,
                     'effective_from':date(2021,1,1),'effective_to':date(2021,2,1),'created_by':'taylor','reason':'Exception'}]
    result=resolve(data,['a'],date(2021,1,1))
    assert [a.policy_id for a in result.assignments if a.category_id==category] == expected
    if action in ('set','add'):
        assert next(a for a in result.assignments if a.category_id==category).explanation.override.reason=='Exception'
    after=resolve(data,['a'],date(2021,2,1))
    data.overrides=[]
    assert after==resolve(data,['a'],date(2021,2,1))


def command(**changes):
    return OverrideCommand(request_id=uuid4(),employee_id='jamie',category_id='pay',policy_id='monthly',
        action='set',effective_from=date(2026,9,12),effective_to=date(2026,10,1),reason='Contract arrangement').model_copy(update=changes)


def test_preview_save_return_to_automatic_and_reconciliation():
    with engine.connect() as connection:
        tx=connection.begin()
        try:
            seed(connection)
            original=stored_intervals(connection,['jamie'])
            proposal=command()
            preview=plan_override(load_inputs(connection),proposal,date(2026,9,12))[0]
            assert stored_intervals(connection,['jamie'])==original
            assert connection.execute(text('SELECT count(*) FROM employee_assignment_overrides')).scalar()==0
            saved=save_override(connection,proposal,date(2026,9,12))
            assert saved.after==preview.after
            assert reconcile(connection,['jamie'])==0
            after=resolve(load_inputs(connection),['jamie'],date(2026,9,12))
            assert next(a for a in after.assignments if a.category_id=='pay').policy_id=='monthly'
            end=command(action='end',policy_id=None,target_override_id=str(proposal.request_id),effective_from=date(2026,9,20),effective_to=None)
            save_override(connection,end,date(2026,9,12))
            after=resolve(load_inputs(connection),['jamie'],date(2026,9,20))
            assert next(a for a in after.assignments if a.category_id=='pay').policy_id=='biweekly'
            assert connection.execute(text('SELECT superseded_at FROM employee_assignment_overrides WHERE id=:id'),{'id':str(proposal.request_id)}).scalar() is not None
        finally:
            tx.rollback()


def test_invalid_overrides_and_database_overlap_leave_no_partial_writes():
    with engine.connect() as connection:
        tx=connection.begin()
        try:
            seed(connection)
            original=stored_intervals(connection,['jamie'])
            for invalid in (command(action='clear',policy_id=None),command(policy_id='github'),command(effective_from=date(2020,1,1))):
                with pytest.raises(ValueError):
                    with connection.begin_nested():
                        save_override(connection,invalid,date(2026,9,12))
                assert stored_intervals(connection,['jamie'])==original
            proposal=command()
            save_override(connection,proposal,date(2026,9,12))
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(text('''INSERT INTO employee_assignment_overrides
                        (id,employment_id,category_id,policy_id,is_single,action,effective_from,effective_to,created_by,reason)
                        SELECT 'conflict',employment_id,category_id,policy_id,is_single,action,effective_from,effective_to,created_by,reason
                        FROM employee_assignment_overrides WHERE id=:id'''),{'id':str(proposal.request_id)})
            # Failure after writing the revision must still roll back the entire save.
            with pytest.raises(RuntimeError):
                with connection.begin_nested():
                    save_override(connection,command(policy_id='biweekly'),date(2026,9,12))
                    raise RuntimeError('Simulated failure before commit')
            assert next(a for a in resolve(load_inputs(connection),['jamie'],date(2026,9,12)).assignments if a.category_id=='pay').policy_id=='monthly'
        finally:
            tx.rollback()


def test_exclusion_survives_recompute_and_employment_end_is_enforced():
    with engine.connect() as connection:
        tx=connection.begin()
        try:
            seed(connection)
            save_override(connection,command(category_id='apps',policy_id='github',action='exclude'),date(2026,9,12))
            reconcile(connection,['jamie'])
            assert 'github' not in [a.policy_id for a in resolve(load_inputs(connection),['jamie'],date(2026,9,12)).assignments]
            data=load_inputs(connection)
            next(j for j in data.jobs if j['employee_id']=='jamie')['effective_to']=date(2026,9,15)
            with pytest.raises(ValueError,match='end date'):
                plan_override(data,command(),date(2026,9,12))
        finally:
            tx.rollback()
