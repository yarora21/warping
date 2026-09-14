"""One in-memory change plan drives both preview and transactional save."""
from copy import deepcopy
from datetime import date
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
from sqlalchemy import text
from app.assignments import load_inputs, reconcile
from app.resolver import Inputs, Interval, active, resolve_timeline


class OverrideCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    employee_id: str
    category_id: str
    policy_id: str | None = None
    action: Literal['set','add','exclude','clear','end']
    target_override_id: str | None = None
    effective_from: date
    effective_to: date | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def valid_dates(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError('A reason is required')
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError('End date must be after the start date')
        return self


class OverrideView(BaseModel):
    id: str
    employment_id: str
    category_id: str
    policy_id: str | None
    action: Literal['set','add','exclude','clear']
    effective_from: date
    effective_to: date | None
    reason: str
    created_by: str


class OverrideImpact(BaseModel):
    before: list[Interval]
    after: list[Interval]
    overrides: list[OverrideView]
    saved: bool = False


def plan_override(inputs: Inputs, command: OverrideCommand, today: date, *, validate_coverage=True):
    if command.effective_from < today:
        raise ValueError('Choose today or a future effective date')
    category = next((c for c in inputs.categories if c['id']==command.category_id),None)
    job = next((j for j in inputs.jobs if j['employee_id']==command.employee_id and active(j,command.effective_from)),None)
    if category is None or job is None:
        raise ValueError('Choose a category and a date within this employee’s employment')
    if job['effective_to'] is not None and (command.effective_to is None or command.effective_to>job['effective_to']) and command.action!='end':
        raise ValueError('Set an end date within this employment period')
    allowed = {'exactly_one': ('set','end'), 'at_most_one': ('set','clear','end'), 'many': ('add','exclude','end')}
    if command.action not in allowed[category['cardinality']]:
        raise ValueError('This action is not allowed for this category')
    if command.action in ('clear','end'):
        if command.policy_id is not None or (command.action=='end' and command.effective_to is not None):
            raise ValueError('Do not select a policy or expiration when returning to automatic assignment')
    elif not any(p['policy_id']==command.policy_id and p['category_id']==category['id'] and active(p,command.effective_from) for p in inputs.policies):
        raise ValueError('Choose an available policy in this category')
    if command.action!='end' and command.target_override_id is not None:
        raise ValueError('An override target is only used for returning to automatic assignment')
    if any(o['id']==str(command.request_id) for o in inputs.overrides):
        raise ValueError('This change has already been saved. Refresh assignments.')
    updated = deepcopy(inputs)
    scope = [o for o in inputs.overrides if o['employment_id']==job['employment_id'] and o['category_id']==category['id']
             and (category['cardinality']!='many' or o['policy_id']==command.policy_id)]
    if command.action=='end':
        prior = next((o for o in inputs.overrides if o['id']==command.target_override_id
                      and o['employment_id']==job['employment_id'] and o['category_id']==category['id']),None)
        if prior is None or not active(prior,command.effective_from):
            raise ValueError('The override is no longer active on that date. Refresh assignments.')
        replaced = [prior]
    else:
        overlaps = [o for o in scope if (o['effective_to'] is None or command.effective_from<o['effective_to'])
                    and (command.effective_to is None or o['effective_from']<command.effective_to)]
        if any(o['effective_from']>command.effective_from for o in overlaps):
            raise ValueError('This period conflicts with a scheduled override. Choose a nonoverlapping period.')
        replaced = overlaps
    inserts = []
    for prior in replaced:
        updated.overrides = [o for o in updated.overrides if o['id']!=prior['id']]
        if prior['effective_from']<command.effective_from:
            shortened = {**prior, 'id': f'{command.request_id}_prior', 'effective_to':command.effective_from}
            inserts.append(shortened)
    if command.action!='end':
        inserts.append({'id':str(command.request_id), 'employment_id':job['employment_id'], 'category_id':category['id'],
                        'policy_id':command.policy_id,'action':command.action, 'effective_from':command.effective_from,
                        'effective_to':command.effective_to, 'created_by':'taylor', 'reason':command.reason,
                        'is_single':category['cardinality']!='many'})
    updated.overrides.extend(inserts)
    before, _ = resolve_timeline(inputs,command.employee_id)
    after, gaps = resolve_timeline(updated,command.employee_id)
    if gaps and validate_coverage:
        raise ValueError(gaps[0].message)
    impact = OverrideImpact(before=[i for i in before if i.category_id==category['id']],
                            after=[i for i in after if i.category_id==category['id']],
                            overrides=[OverrideView.model_validate(o) for o in updated.overrides if o['employment_id']==job['employment_id']])
    return impact, replaced, inserts


def save_override(connection, command: OverrideCommand, today: date) -> OverrideImpact:
    # Caller owns assignment_transaction(); every save reloads and revalidates.
    impact, replaced, inserts = plan_override(load_inputs(connection),command,today)
    write_override_rows(connection, replaced, inserts, command.reason)
    reconcile(connection,[command.employee_id],reason=command.reason)
    impact.saved = True
    return impact


def write_override_rows(connection, replaced, inserts, reason):
    for prior in replaced:
        connection.execute(text('''UPDATE employee_assignment_overrides
            SET superseded_at=now(),superseded_by='taylor',superseded_reason=:reason WHERE id=:id'''),
            {'reason':reason,'id':prior['id']})
    for row in inserts:
        connection.execute(text('''INSERT INTO employee_assignment_overrides
            (id,employment_id,category_id,policy_id,is_single,action,effective_from,effective_to,created_by,reason)
            VALUES (:id,:employment_id,:category_id,:policy_id,:is_single,:action,:effective_from,:effective_to,:created_by,:reason)'''),row)
