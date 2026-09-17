from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.assignments import load_inputs, reconcile, stored_intervals
from app.database import engine
from app.overrides import OverrideCommand, save_override
from app.resolver import resolve
from app.rules import PolicyCommand, RuleCommand, create_policy, plan_rule, rule_fields, save_rule
from app.seed import seed

TODAY = date(2026,9,12)
FUTURE = date(2026,10,1)


@pytest.fixture
def company():
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            seed(connection)
            yield connection
        finally:
            transaction.rollback()


def command(**changes):
    return RuleCommand(**{'request_id':uuid4(),'action':'create','category_id':'apps','effective_from':TODAY,
        'reason':'Test rule','name':'Engineering app','policy_id':'github',
        'conditions':{'all':[{'field':'department_id','operator':'equals','value':'engineering'}]},**changes})


def policies(connection, employee, day):
    return {a.policy_id for a in resolve(load_inputs(connection),[employee],day).assignments}


def test_policy_creation_rule_edit_former_matches_and_end(company):
    created = create_policy(company,PolicyCommand(request_id=uuid4(),category_id='apps',name='Notion',description='Team wiki',effective_from=TODAY,reason='New tool'),TODAY)
    assert created.id not in policies(company,'jamie',TODAY)
    add = command(policy_id=created.id)
    before = stored_intervals(company)
    preview = plan_rule(load_inputs(company),add,TODAY,rule_fields(company))[0]
    assert stored_intervals(company)==before
    saved = save_rule(company,add,TODAY)
    assert saved.changes==preview.changes
    assert created.id in policies(company,'jamie',TODAY)
    edit = command(action='edit',rule_id=str(add.request_id),policy_id=created.id,effective_from=FUTURE,
        conditions={'all':[{'field':'department_id','operator':'equals','value':'sales'}]})
    impact = save_rule(company,edit,TODAY)
    assert any(c.employee_id=='jamie' and c.lost==['Notion'] for c in impact.changes)
    assert any(c.employee_id=='oliver' and c.gained==['Notion'] for c in impact.changes)
    assert created.id in policies(company,'jamie',TODAY)
    assert created.id not in policies(company,'jamie',FUTURE)
    assert created.id in policies(company,'oliver',FUTURE)
    # On the scheduled date, end the now-active rule with a new dated revision.
    end = RuleCommand(request_id=uuid4(),action='end',category_id='apps',rule_id=str(add.request_id),effective_from=date(2026,10,2),reason='End wiki access')
    save_rule(company,end,FUTURE)
    assert created.id not in policies(company,'oliver',date(2026,10,2))
    assert reconcile(company)==0
    assert company.execute(text('SELECT superseded_at FROM assignment_rule_versions WHERE id=:id'),{'id':str(add.request_id)}).scalar() is not None


def test_reorder_history_manual_exceptions_and_scheduled_conflicts(company):
    save_override(company,OverrideCommand(request_id=uuid4(),employee_id='jamie',category_id='pay',policy_id='biweekly',action='set',effective_from=TODAY,reason='Keep pay'),TODAY)
    order = RuleCommand(request_id=uuid4(),action='reorder',category_id='pay',effective_from=FUTURE,reason='Default first',ordered_rule_ids=['pay_default','pay_us'])
    impact = save_rule(company,order,TODAY)
    assert 'biweekly' in policies(company,'alex',TODAY)
    assert 'monthly' in policies(company,'alex',FUTURE)
    assert 'biweekly' in policies(company,'jamie',FUTURE)
    assert any(m.employee_id=='jamie' for m in impact.preserved_manual)
    assert not any(c.employee_id=='jamie' for c in impact.changes)
    with pytest.raises(ValueError,match='scheduled version'):
        save_rule(company,order.model_copy(update={'request_id':uuid4(),'effective_from':TODAY}),TODAY)
    assert reconcile(company)==0


def test_gap_rejection_and_atomic_rollback(company):
    end = RuleCommand(request_id=uuid4(),action='end',category_id='pay',rule_id='pay_default',effective_from=FUTURE,reason='Remove fallback')
    original = stored_intervals(company)
    impact = plan_rule(load_inputs(company),end,TODAY,rule_fields(company))[0]
    assert impact.gaps
    with pytest.raises(ValueError,match='Required assignments'):
        with company.begin_nested():
            save_rule(company,end,TODAY)
    assert stored_intervals(company)==original
    with pytest.raises(RuntimeError):
        with company.begin_nested():
            save_rule(company,command(),TODAY)
            raise RuntimeError('Before commit')
    assert stored_intervals(company)==original


def test_validation_and_scheduled_policy_availability(company):
    for condition in ({'field':'department_id','operator':'equals','value':'Engineering'},
                      {'field':'group_ids','operator':'in','value':['missing']},
                      {'field':'country','operator':'equals','value':'USA'}):
        with pytest.raises(ValueError):
            plan_rule(load_inputs(company),command(conditions={'all':[condition]}),TODAY,rule_fields(company))
    with pytest.raises(ValidationError):
        command(conditions={'all':[{'field':'tenure_months','operator':'in','value':[24]}]})
    policy = create_policy(company,PolicyCommand(request_id=uuid4(),category_id='apps',name='Future tool',description='Later',effective_from=FUTURE,reason='Scheduled launch'),TODAY)
    with pytest.raises(ValueError,match='entire period'):
        save_rule(company,command(policy_id=policy.id),TODAY)
    save_rule(company,command(policy_id=policy.id,effective_from=FUTURE),TODAY)
    assert policy.id not in policies(company,'jamie',TODAY)
    assert policy.id in policies(company,'jamie',FUTURE)


def test_save_revalidates_and_group_rule_uses_ids(company):
    proposal = command(conditions={'all':[{'field':'group_ids','operator':'in','value':['launch']}]},policy_id='slack')
    preview = plan_rule(load_inputs(company),proposal,TODAY,rule_fields(company))[0]
    save_override(company,OverrideCommand(request_id=uuid4(),employee_id='jamie',category_id='apps',policy_id='github',action='exclude',effective_from=TODAY,reason='Access exception'),TODAY)
    saved = save_rule(company,proposal,TODAY)
    assert not saved.changes and not preview.changes  # Slack already applies; multiple rules deduplicate.
    assert 'github' not in policies(company,'jamie',TODAY)
    assert any(m.employee_id=='jamie' and m.action=='exclude' for m in saved.preserved_manual)
    assert reconcile(company)==0
