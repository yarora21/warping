from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.assignments import load_inputs, reconcile, stored_intervals
from app.database import engine
from app.employees import EmployeeCommand, employee_facts, options, plan_employee, save_employee
from app.overrides import OverrideCommand, save_override
from app.resolver import resolve
from app.seed import seed

TODAY = date(2026,9,12)
MOVE = date(2026,10,1)


@pytest.fixture
def company():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            seed(connection)
            yield connection
        finally:
            transaction.rollback()


def edit(connection, employee='jamie', **changes):
    facts = employee_facts(load_inputs(connection),employee,TODAY).model_dump()
    return EmployeeCommand(**{**facts,'request_id':uuid4(),'employee_id':employee,
        'effective_from':MOVE,'reason':'Employee update',**changes})


def policies(connection, employee, day):
    return {a.policy_id for a in resolve(load_inputs(connection),[employee],day).assignments}


def new_hire(**changes):
    return EmployeeCommand(**{'request_id':uuid4(),'name':'New Person','email':'new@example.com',
        'effective_from':MOVE,'reason':'New hire','country':'GB','department_id':'engineering',
        'employment_type':'salaried','manager_id':'sam','group_ids':['launch'],**changes})


def test_dated_move_and_group_removal_preserve_manual_pay_and_history(company):
    save_override(company,OverrideCommand(request_id=uuid4(),employee_id='jamie',category_id='pay',policy_id='monthly',
        action='set',effective_from=TODAY,reason='Agreed pay schedule'),TODAY)
    previous = policies(company,'jamie',TODAY)
    original_rows = stored_intervals(company,['jamie'])
    command = edit(company,state='CA',group_ids=[])
    preview = plan_employee(load_inputs(company),command,TODAY,options(company)).impact
    assert stored_intervals(company,['jamie']) == original_rows
    saved = save_employee(company,command,TODAY)
    assert saved.after == preview.after
    assert policies(company,'jamie',TODAY) == previous
    assert 'figma' not in policies(company,'jamie',MOVE)
    assert {'monthly','ca_meal'} <= policies(company,'jamie',MOVE)
    assert reconcile(company,saved.affected_employee_ids) == 0
    assert company.execute(text("SELECT superseded_at FROM employee_versions WHERE id='attributes_jamie_1'")).scalar() is not None
    with pytest.raises(ValueError,match='scheduled edit'):
        save_employee(company,edit(company,state='WA'),TODAY)


def test_manager_reconciliation_loses_last_report_and_gains_first(company):
    # Move both of Taylor's reports; Oliver starts with no reports.
    save_employee(company,edit(company,'amara',manager_id='oliver'),TODAY)
    command = edit(company,'zoe',manager_id='oliver')
    result = save_employee(company,command,TODAY)
    assert set(result.affected_employee_ids) == {'zoe','taylor','oliver'}
    assert 'manager' in policies(company,'taylor',TODAY)
    assert 'manager' not in policies(company,'taylor',MOVE)
    assert 'manager' in policies(company,'oliver',MOVE)
    for employee in result.affected_employee_ids:
        stored = {i.policy_id for _,i in stored_intervals(company,[employee]) if i.effective_from<=MOVE and (not i.effective_to or i.effective_to>MOVE)}
        assert stored == policies(company,employee,MOVE)


@pytest.mark.parametrize('onboarding', [True,False])
def test_coverage_gap_requires_inline_fix_and_saves_atomically(company,onboarding):
    # Keep historical default coverage, but remove it from the planned change onward.
    company.execute(text("UPDATE assignment_rule_versions SET superseded_at=now(),superseded_by='taylor',superseded_reason='Test coverage' WHERE rule_id='pay_default'"))
    company.execute(text("""INSERT INTO assignment_rule_versions
        (id,rule_id,name,policy_id,priority,conditions,effective_from,effective_to,created_by,change_reason)
        SELECT 'default_until_move',rule_id,name,policy_id,priority,conditions,effective_from,:end,'taylor','Test coverage'
        FROM assignment_rule_versions WHERE rule_id='pay_default'"""),{'end':MOVE})
    command = new_hire() if onboarding else edit(company,country='GB',state=None)
    preview = plan_employee(load_inputs(company),command,TODAY,options(company)).impact
    assert any(g.category_id=='pay' and g.employee_id==preview.employee_id for g in preview.gaps)
    before = company.execute(text('SELECT count(*) FROM employees')).scalar()
    with pytest.raises(ValueError,match='Required assignments'):
        with company.begin_nested():
            save_employee(company,command,TODAY)
    assert company.execute(text('SELECT count(*) FROM employees')).scalar()==before
    # Use a US manager so their required coverage is unaffected by the test rule change.
    fixed = EmployeeCommand.model_validate({**command.model_dump(),'coverage_fixes':[
        {'category_id':'pay','policy_id':'monthly','reason':'International pay arrangement'}]})
    saved = save_employee(company,fixed,TODAY)
    assert not saved.gaps
    assert 'monthly' in policies(company,saved.employee_id,MOVE)
    assert company.execute(text('SELECT count(*) FROM employees')).scalar()==before+int(onboarding)
    assert reconcile(company,saved.affected_employee_ids)==0


def test_onboarding_future_directory_and_rollback(company):
    command = new_hire()
    preview = plan_employee(load_inputs(company),command,TODAY,options(company)).impact
    assert all(a.employee_id != preview.employee_id for a in preview.before)
    with pytest.raises(RuntimeError):
        with company.begin_nested():
            save_employee(company,command,TODAY)
            raise RuntimeError('Failure before commit')
    assert not company.execute(text('SELECT 1 FROM employees WHERE id=:id'),{'id':preview.employee_id}).scalar()
    saved = save_employee(company,command,TODAY)
    assert saved.after==preview.after
    assert policies(company,saved.employee_id,TODAY)==set()
    assert {'monthly','github','figma'} <= policies(company,saved.employee_id,MOVE)
    from app.queries import people
    person = next(p for p in people(company,TODAY) if p.id==saved.employee_id)
    assert person.status=='upcoming'
    assert person.groups==['Launch team']


def test_invalid_edits_and_save_revalidation(company):
    for command in (edit(company,effective_from=date(2020,1,1)),edit(company,department_id='missing'),
                    edit(company,group_ids=['missing']),edit(company,manager_id='jamie'),
                    edit(company,'alex',manager_id='jamie')):
        with pytest.raises(ValueError):
            plan_employee(load_inputs(company),command,TODAY,options(company))
    command = edit(company,state='CA')
    preview = plan_employee(load_inputs(company),command,TODAY,options(company)).impact
    save_override(company,OverrideCommand(request_id=uuid4(),employee_id='jamie',category_id='pay',policy_id='monthly',
        action='set',effective_from=TODAY,reason='Changed while preview open'),TODAY)
    saved = save_employee(company,command,TODAY)
    assert saved.after != preview.after
    assert 'monthly' in policies(company,'jamie',MOVE)


def test_employee_history_groups_real_dated_changes_and_hires(company):
    from app.employee_history import employee_history
    initial = employee_history(company,'jamie')
    assert len(initial)==1 and initial[0].title=='Hired'
    original_hire_reason=initial[0].reasons
    save_employee(company,edit(company,state='CA',department_id='sales',manager_id='sam',group_ids=[],reason='Team relocation'),TODAY)
    history=employee_history(company,'jamie')
    assert len(history)==2 and history[0].effective_date==MOVE
    assert history[-1].reasons==original_hire_reason
    changes={c.field:(c.before,c.after) for c in history[0].changes}
    assert changes=={'Location':('NY, US','CA, US'),'Department':('Engineering','Sales'),
                     'Manager':('Alex Chen','Sam Rivera'),'Groups':('Launch team','No groups')}
    assert len(history[0].reasons)==1 and history[0].reasons[0].reason=='Team relocation'
    assert history[0].reasons[0].actor=='Taylor Brooks'
    # Group-only removal has no new attribute revision, but still has its own milestone.
    save_employee(company,edit(company,'morgan',group_ids=[],reason='Launch finished'),TODAY)
    group_event=employee_history(company,'morgan')[0]
    assert group_event.title=='Groups changed' and group_event.reasons[0].reason=='Launch finished'
    hired=save_employee(company,new_hire(),TODAY)
    new_history=employee_history(company,hired.employee_id)
    assert len(new_history)==1 and new_history[0].title=='Hired' and new_history[0].effective_date==MOVE
    assert next(c for c in new_history[0].changes if c.field=='Groups').after=='Launch team'
