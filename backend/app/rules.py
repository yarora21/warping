"""Small policy/rule commands, using the same resolver and transaction boundary."""
from copy import deepcopy
from datetime import date
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

from app.assignments import load_inputs, reconcile
from app.employees import Choice, options
from app.resolver import FIELDS, Conditions, Gap, Interval, active, resolve_timeline


class PolicyCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: UUID
    category_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    effective_from: date
    reason: str = Field(min_length=1, max_length=1000)


class PolicyCreated(BaseModel):
    id: str
    name: str


class RuleCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: UUID
    action: Literal['create','edit','end','reorder']
    category_id: str
    effective_from: date
    reason: str = Field(min_length=1, max_length=1000)
    rule_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    policy_id: str | None = None
    conditions: Conditions | None = None
    ordered_rule_ids: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def shape(self):
        if self.action in ('create','edit'):
            if not self.name or self.policy_id is None or self.conditions is None:
                raise ValueError('Choose a name, policy, and conditions')
        elif self.name is not None or self.policy_id is not None or self.conditions is not None:
            raise ValueError('Ending or reordering does not change a rule’s conditions')
        if (self.action in ('edit','end')) != (self.rule_id is not None):
            raise ValueError('Select a rule only when editing or ending it')
        if self.action != 'reorder' and self.ordered_rule_ids:
            raise ValueError('Rule ordering is a separate change')
        return self


class FieldView(BaseModel):
    id: str
    label: str
    kind: str
    operators: list[str]
    choices: list[Choice]


def rule_fields(connection) -> list[FieldView]:
    catalogs = options(connection)
    choices = {'department_id':catalogs.departments, 'group_ids':catalogs.groups,
               'employment_type':[Choice(id=k,name=v) for k,v in (
                   ('salaried','Salaried employee'),('hourly','Hourly employee'),('contractor','Contractor'))]}
    return [FieldView(id=key,label=spec.label,kind=spec.kind,operators=list(spec.operators),choices=choices.get(key,[]))
            for key,spec in FIELDS.items()]


class AssignmentDelta(BaseModel):
    employee_id: str
    effective_from: date
    effective_to: date | None
    gained: list[str]
    lost: list[str]


class PreservedManual(BaseModel):
    employee_id: str
    policy_name: str
    action: str


class RuleImpact(BaseModel):
    changes: list[AssignmentDelta]
    preserved_manual: list[PreservedManual]
    gaps: list[Gap]
    saved: bool = False


def create_policy(connection, command: PolicyCommand, today: date) -> PolicyCreated:
    if command.effective_from < today:
        raise ValueError('Choose today or a future policy start date')
    inputs = load_inputs(connection)
    if not any(c['id']==command.category_id for c in inputs.categories):
        raise ValueError('Choose an existing category')
    if any(p['category_id']==command.category_id and p['name'].casefold()==command.name.casefold() for p in inputs.policies):
        raise ValueError('A policy with this name already exists in the category')
    row = {**command.model_dump(),'id':str(command.request_id)}
    connection.execute(text('INSERT INTO policies (id,category_id) VALUES (:id,:category_id)'),row)
    connection.execute(text('''INSERT INTO policy_versions
        (id,policy_id,name,description,effective_from,created_by,change_reason)
        VALUES (:id,:id,:name,:description,:effective_from,'taylor',:reason)'''),row)
    # Creating a policy never grants it implicitly. Rules or manual exceptions do that.
    reconcile(connection,reason=command.reason)
    return PolicyCreated(id=row['id'],name=command.name)


def assignment_diff(before: list[Interval], after: list[Interval], employee_id: str, start: date) -> list[AssignmentDelta]:
    boundaries = sorted({start} | {day for i in before+after for day in (i.effective_from,i.effective_to) if day and day>start})
    result = []
    for index, day in enumerate(boundaries):
        old = {i.policy_id:i.explanation.policy_name for i in before if i.effective_from<=day and (not i.effective_to or day<i.effective_to)}
        new = {i.policy_id:i.explanation.policy_name for i in after if i.effective_from<=day and (not i.effective_to or day<i.effective_to)}
        gained, lost = sorted(new[k] for k in new.keys()-old.keys()), sorted(old[k] for k in old.keys()-new.keys())
        end = boundaries[index+1] if index+1<len(boundaries) else None
        if gained or lost:
            if result and result[-1].effective_to==day and result[-1].gained==gained and result[-1].lost==lost:
                result[-1].effective_to=end
            else:
                result.append(AssignmentDelta(employee_id=employee_id,effective_from=day,effective_to=end,gained=gained,lost=lost))
    return result


def plan_rule(inputs, command: RuleCommand, today: date, fields: list[FieldView]):
    if command.effective_from < today:
        raise ValueError('Choose today or a future effective date')
    category = next((c for c in inputs.categories if c['id']==command.category_id),None)
    if category is None:
        raise ValueError('Choose an existing category')
    if command.conditions:
        choices = {f.id:{c.id for c in f.choices} for f in fields}
        for condition in command.conditions.all:
            values = condition.value if isinstance(condition.value,list) else [condition.value]
            if condition.field in ('department_id','group_ids','employment_type') and any(v not in choices[condition.field] for v in values):
                raise ValueError('Choose existing departments, groups, and employment types')
            if condition.field in ('country','state') and any(not isinstance(v,str) or not v.strip() or v!=v.strip().upper() for v in values):
                raise ValueError('Use uppercase location codes, such as US or CA')
            if condition.field=='country' and any(len(v)!=2 or not v.isalpha() for v in values):
                raise ValueError('Use two-letter country codes')
    prefix = str(command.request_id)
    if any(r['id'].startswith(prefix) for r in inputs.rules):
        raise ValueError('This rule change has already been saved. Refresh the rules.')
    policy_ids = {p['policy_id'] for p in inputs.policies if p['category_id']==category['id']}
    category_rules = [r for r in inputs.rules if r['policy_id'] in policy_ids]
    current = sorted([r for r in category_rules if active(r,command.effective_from)],key=lambda r:(r['priority'],r['rule_id']))
    selected = next((r for r in current if r['rule_id']==command.rule_id),None)
    if command.action in ('edit','end') and selected is None:
        raise ValueError('Choose a rule active in this category on the effective date')
    targets = current if command.action=='reorder' else [selected] if selected else []
    ids = {r['rule_id'] for r in targets}
    if any(r['rule_id'] in ids and r['effective_from']>today for r in category_rules):
        raise ValueError('An affected rule has a scheduled version. Editing or reordering that schedule is not supported yet.')
    if command.action=='reorder':
        if len(command.ordered_rule_ids)!=len(set(command.ordered_rule_ids)) or set(command.ordered_rule_ids)!=ids:
            raise ValueError('The category’s rules changed. Reload the list and arrange it again.')
    end = selected['effective_to'] if selected else None
    if command.action in ('create','edit'):
        policy_versions = sorted([p for p in inputs.policies if p['policy_id']==command.policy_id and p['category_id']==category['id']],key=lambda p:p['effective_from'])
        cursor = command.effective_from
        for policy in policy_versions:
            if active(policy,cursor):
                cursor = policy['effective_to']
                if cursor is None or (end is not None and cursor>=end):
                    break
        if cursor is not None and (end is None or cursor<end):
            raise ValueError('Choose a policy available for the rule’s entire period')
    updated = deepcopy(inputs)
    inserts, replaced = [], []
    metadata = {'created_by':'taylor','change_reason':command.reason}
    if command.action=='create':
        inserts.append({'id':prefix,'rule_id':prefix,'name':command.name,'policy_id':command.policy_id,
            'priority':max((r['priority'] for r in category_rules),default=0)+10,'conditions':command.conditions.model_dump(),
            'effective_from':command.effective_from,'effective_to':None,**metadata})
    else:
        for index, prior in enumerate(targets):
            priority = (command.ordered_rule_ids.index(prior['rule_id'])+1)*10 if command.action=='reorder' else prior['priority']
            if command.action=='reorder' and priority==prior['priority']:
                continue
            replaced.append(prior)
            if prior['effective_from']<command.effective_from:
                inserts.append({**prior,'id':f'{prefix}_prior_{index}','effective_to':command.effective_from,**metadata})
            if command.action!='end':
                inserts.append({**prior,'id':f'{prefix}_next_{index}','effective_from':command.effective_from,
                    'priority':priority,**({'name':command.name,'policy_id':command.policy_id,'conditions':command.conditions.model_dump()} if command.action=='edit' else {}),**metadata})
    updated.rules = [r for r in updated.rules if r['id'] not in {p['id'] for p in replaced}] + inserts
    changes, gaps, preserved = [], [], set()
    # Whole-company recomputation includes former matches, not only newly matching employees.
    for employee in inputs.employees:
        before, _ = resolve_timeline(inputs,employee['id'])
        after, missing = resolve_timeline(updated,employee['id'])
        gaps.extend(missing)
        changes.extend(assignment_diff(before,after,employee['id'],command.effective_from))
    jobs = {j['employment_id']:j['employee_id'] for j in inputs.jobs}
    for override in inputs.overrides:
        if override['category_id']==category['id'] and (not override['effective_to'] or override['effective_to']>command.effective_from):
            name = next((p['name'] for p in inputs.policies if p['policy_id']==override['policy_id'] and active(p,override['effective_from'])), 'No policy')
            preserved.add((jobs[override['employment_id']],name,override['action']))
    impact = RuleImpact(changes=changes,gaps=gaps,preserved_manual=[PreservedManual(employee_id=e,policy_name=p,action=a) for e,p,a in sorted(preserved)])
    return impact, replaced, inserts


def save_rule(connection, command: RuleCommand, today: date) -> RuleImpact:
    impact, replaced, inserts = plan_rule(load_inputs(connection),command,today,rule_fields(connection))
    if impact.gaps:
        raise ValueError('Required assignments would be missing. Keep a fallback rule or add manual assignments for the affected employees before saving.')
    if command.action=='create':
        connection.execute(text('INSERT INTO assignment_rules (id) VALUES (:id)'),{'id':str(command.request_id)})
    for row in replaced:
        connection.execute(text("UPDATE assignment_rule_versions SET superseded_at=now(),superseded_by='taylor',superseded_reason=:reason WHERE id=:id"),{'id':row['id'],'reason':command.reason})
    for row in inserts:
        connection.execute(text('''INSERT INTO assignment_rule_versions
            (id,rule_id,name,policy_id,priority,conditions,effective_from,effective_to,created_by,change_reason)
            VALUES (:id,:rule_id,:name,:policy_id,:priority,CAST(:conditions AS jsonb),:effective_from,:effective_to,:created_by,:change_reason)'''),
            {**row,'conditions':json.dumps(row['conditions'])})
    reconcile(connection,reason=command.reason)
    impact.saved = True
    return impact
