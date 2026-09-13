from datetime import date
import pytest
from pydantic import ValidationError
from app.resolver import Conditions, Inputs, active, resolve, resolve_timeline


def inputs():
    start = date(2020, 2, 29)
    period = {'effective_from': start, 'effective_to': None}
    return Inputs(
        employees=[{'id': 'a'}],
        jobs=[dict(period, id='job_v1', employee_id='a', employment_id='job_a')],
        attributes=[dict(period, id='attr_v1', employment_id='job_a', manager_id=None,
                         country='US', state='CA', employment_type='hourly', department_id='eng')],
        memberships=[dict(period, id='member_v1', employment_id='job_a', group_id='launch')],
        categories=[{'id': 'pay', 'name': 'Pay', 'cardinality': 'exactly_one'},
                    {'id': 'apps', 'name': 'Apps', 'cardinality': 'many'}],
        policies=[dict(period, id='p1', policy_id='monthly', category_id='pay', name='Monthly'),
                  dict(period, id='p2', policy_id='biweekly', category_id='pay', name='Biweekly'),
                  dict(period, id='p3', policy_id='github', category_id='apps', name='GitHub')],
        rules=[dict(period, id='r1', rule_id='default', policy_id='monthly', name='Default', priority=100, conditions={'all': []})],
    )


def rule(data, name, policy='biweekly', priority=10, conditions=None):
    return dict(effective_from=date(2020,2,29), effective_to=None, id=name+'_v1', rule_id=name,
                policy_id=policy, name=name, priority=priority, conditions={'all': conditions or []})


@pytest.mark.parametrize('field,operator,value,matched', [
    ('country','equals','US',True), ('country','in',['GB'],False),
    ('state','equals','CA',True), ('department_id','equals','eng',True),
    ('employment_type','in',['hourly','salaried'],True), ('group_ids','in',['launch'],True),
    ('is_manager','equals',True,False), ('tenure_months','gte',12,True),
    ('tenure_months','lt',12,False), ('tenure_months','equals',12,True),
])
def test_registry_conditions(field,operator,value,matched):
    data = inputs()
    data.rules.append(rule(data,'conditional',conditions=[{'field':field,'operator':operator,'value':value}]))
    result = resolve(data,['a'],date(2021,2,28))
    assert result.assignments[0].policy_id == ('biweekly' if matched else 'monthly')


@pytest.mark.parametrize('condition', [
    {'field':'unknown','operator':'equals','value':'x'},
    {'field':'country','operator':'sql','value':'x'},
    {'field':'tenure_months','operator':'gte','value':True},
    {'field':'group_ids','operator':'in','value':'launch'},
])
def test_reject_unsupported_conditions(condition):
    with pytest.raises(ValidationError):
        Conditions.model_validate({'all':[condition]})


def test_priority_tie_and_many_sources_are_deterministic():
    data = inputs()
    data.rules += [rule(data,'z_rule'), rule(data,'a_rule',policy='monthly'),
                   rule(data,'app_a',policy='github'), rule(data,'app_b',policy='github')]
    expected = resolve(data,['a','a'],date(2022,1,1))
    data.rules.reverse()
    assert resolve(data,['a'],date(2022,1,1)) == expected
    pay = next(a for a in expected.assignments if a.category_id == 'pay')
    app = next(a for a in expected.assignments if a.category_id == 'apps')
    assert pay.policy_id == 'monthly' and pay.explanation.tie_broken
    assert pay.explanation.source_rule_version_ids == ['a_rule_v1']
    assert app.explanation.source_rule_version_ids == ['app_a_v1','app_b_v1']


def test_complete_timeline_equality_threshold_and_final_interval():
    data = inputs()
    data.rules.append(rule(data,'one_month',conditions=[{'field':'tenure_months','operator':'equals','value':12}]))
    intervals, gaps = resolve_timeline(data,'a')
    assert not gaps
    assert [(i.policy_id,i.effective_from,i.effective_to) for i in intervals] == [
        ('monthly',date(2020,2,29),date(2021,2,28)),
        ('biweekly',date(2021,2,28),date(2021,3,29)),
        ('monthly',date(2021,3,29),None),
    ]
    for day in (date(2020,2,28),date(2021,2,27),date(2021,2,28),date(2021,3,28),date(2021,3,29),date(2099,1,1)):
        stored = [i.policy_id for i in intervals if active(i.model_dump(),day)]
        assert stored == [a.policy_id for a in resolve(data,['a'],day).assignments]


def test_employment_and_policy_boundaries_and_manager_dependency():
    data = inputs()
    data.jobs[0]['effective_to'] = date(2022,1,1)
    data.policies[0]['effective_to'] = date(2021,1,1)
    assert not resolve(data,['a'],date(2019,1,1)).gaps
    assert resolve(data,['a'],date(2021,1,1)).gaps
    assert not resolve(data,['a'],date(2022,1,1)).gaps
    data.policies[0]['effective_to'] = None
    data.jobs.append(dict(data.jobs[0],id='report_job',employee_id='b',employment_id='job_b',effective_to=date(2021,1,1)))
    data.attributes.append(dict(data.attributes[0],id='report_attr',employment_id='job_b',manager_id='a'))
    data.rules.append(rule(data,'manager',conditions=[{'field':'is_manager','operator':'equals','value':True}]))
    assert resolve(data,['a'],date(2020,12,31)).assignments[0].policy_id == 'biweekly'
    assert resolve(data,['a'],date(2021,1,1)).assignments[0].policy_id == 'monthly'


def test_adjacent_segments_merge_but_provenance_change_does_not():
    data = inputs()
    # Unrelated policy boundary must not fragment an unchanged assignment.
    data.policies.append(dict(data.policies[-1],id='other',policy_id='unused',effective_from=date(2020,5,1)))
    assert len(resolve_timeline(data,'a')[0]) == 1
    data.attributes[0]['effective_to'] = date(2021,1,1)
    data.attributes.append(dict(data.attributes[0],id='attr_v2',effective_from=date(2021,1,1),effective_to=None))
    intervals, _ = resolve_timeline(data,'a')
    assert len(intervals) == 2
    assert intervals[0].policy_id == intervals[1].policy_id
    assert intervals[0].explanation != intervals[1].explanation
