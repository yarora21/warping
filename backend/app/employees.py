"""Dated employee commands. Preview and save share one pure change planner."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

from app.assignments import load_inputs, reconcile
from app.overrides import OverrideCommand, plan_override, write_override_rows
from app.resolver import Gap, Inputs, Interval, active, resolve_timeline, snapshot


class Choice(BaseModel):
    id: str
    name: str


class EmployeeOptions(BaseModel):
    departments: list[Choice]
    groups: list[Choice]


class EmployeeFacts(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    country: str = Field(pattern=r'^[A-Z]{2}$')
    state: str | None = None
    department_id: str
    employment_type: Literal['salaried', 'hourly', 'contractor']
    manager_id: str | None = None
    group_ids: list[str] = Field(default_factory=list)


class CoverageFix(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    category_id: str
    policy_id: str
    reason: str = Field(min_length=1, max_length=1000)


class EmployeeCommand(EmployeeFacts):
    request_id: UUID
    employee_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254, pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    effective_from: date
    reason: str = Field(min_length=1, max_length=1000)
    coverage_fixes: list[CoverageFix] = Field(default_factory=list)

    @model_validator(mode='after')
    def identity(self):
        if self.employee_id is None:
            if not self.name or not self.email:
                raise ValueError('Enter a name and valid email for the new employee')
        elif self.name is not None or self.email is not None:
            raise ValueError('Identity changes are not part of this dated edit')
        if len({f.category_id for f in self.coverage_fixes}) != len(self.coverage_fixes):
            raise ValueError('Choose one manual assignment per required category')
        return self


class EmployeeImpact(BaseModel):
    employee_id: str
    affected_employee_ids: list[str]
    before: list[Interval]
    after: list[Interval]
    gaps: list[Gap]
    saved: bool = False


def options(connection) -> EmployeeOptions:
    return EmployeeOptions(**{table: [dict(r) for r in connection.execute(
        text(f'SELECT id,name FROM {table} ORDER BY name')).mappings()] for table in ('departments','groups')})


def employee_facts(inputs: Inputs, employee_id: str, day: date) -> EmployeeFacts:
    values = snapshot(inputs, employee_id, day)
    if values is None:
        raise ValueError('Choose a date within this employee’s employment')
    return EmployeeFacts(**{key: values[0][key] for key in EmployeeFacts.model_fields})


@dataclass
class EmployeePlan:
    impact: EmployeeImpact
    updated: Inputs
    inserts: dict[str, list[dict]]
    replaced: dict[str, list[dict]]
    override_replaced: list[dict]
    override_inserts: list[dict]


def plan_employee(inputs: Inputs, command: EmployeeCommand, today: date, choices: EmployeeOptions) -> EmployeePlan:
    if command.effective_from < today:
        raise ValueError('Choose today or a future date. Past-start onboarding and historical corrections are not available.')
    if command.department_id not in {d.id for d in choices.departments}:
        raise ValueError('Choose an existing department')
    if set(command.group_ids) - {g.id for g in choices.groups}:
        raise ValueError('Choose existing groups')
    updated = deepcopy(inputs)
    employee_id = command.employee_id or str(command.request_id)
    inserts = {table: [] for table in ('employees','employments','employment_versions','employee_versions','group_memberships')}
    replaced = {table: [] for table in ('employee_versions','group_memberships')}
    prefix = str(command.request_id)
    metadata = {'created_by':'taylor', 'change_reason':command.reason}
    if any(row['id'].startswith(prefix) for rows in (inputs.employees, inputs.attributes, inputs.memberships) for row in rows):
        raise ValueError('This change has already been saved. Refresh the employee.')
    if command.employee_id is None:
        if any(e['email'].lower() == command.email.lower() for e in inputs.employees):
            raise ValueError('An employee with this email already exists')
        employee = {'id':employee_id,'name':command.name,'email':command.email.lower()}
        job = {'id':prefix+'_job_revision','employment_id':prefix+'_job','employee_id':employee_id,
               'effective_from':command.effective_from,'effective_to':None, **metadata}
        inserts['employees'].append(employee)
        inserts['employments'].append({'id':job['employment_id'],'employee_id':employee_id})
        inserts['employment_versions'].append(job)
        updated.employees.append(employee)
        updated.jobs.append(job)
        prior = None
    else:
        job = next((j for j in inputs.jobs if j['employee_id']==employee_id and active(j,command.effective_from)),None)
        if job is None:
            raise ValueError('Choose a date within this employee’s employment')
        versions = [a for a in inputs.attributes if a['employment_id']==job['employment_id']]
        prior = next((a for a in versions if active(a,command.effective_from)),None)
        if prior is None:
            raise ValueError('No employee information is recorded on this date')
        if any(a['effective_from'] > today for a in versions):
            raise ValueError('This employee already has a scheduled edit. Editing that schedule is not supported yet.')
    if command.manager_id is not None and (command.manager_id==employee_id or not any(
            j['employee_id']==command.manager_id and active(j,command.effective_from) for j in updated.jobs)):
        raise ValueError('Choose another employee who is employed on this date as manager')
    fields = command.model_dump(include=set(EmployeeFacts.model_fields)-{'group_ids'})
    fields['state'] = fields['state'] or None
    if prior is None or any(prior[k]!=v for k,v in fields.items()):
        if prior:
            replaced['employee_versions'].append(prior)
            updated.attributes.remove(next(a for a in updated.attributes if a['id']==prior['id']))
            if prior['effective_from'] < command.effective_from:
                inserts['employee_versions'].append({**prior,'id':prefix+'_prior','effective_to':command.effective_from,**metadata})
        inserts['employee_versions'].append({'id':prefix+'_attributes','employment_id':job['employment_id'],
            **fields,'effective_from':command.effective_from,'effective_to':job['effective_to'],**metadata})
        updated.attributes.extend(inserts['employee_versions'])
    members = [m for m in inputs.memberships if m['employment_id']==job['employment_id']]
    current = {m['group_id'] for m in members if active(m,command.effective_from)}
    desired = set(command.group_ids)
    # A full membership selection must not silently erase or reinterpret scheduled changes.
    if any(m['effective_from'] > today or (m['effective_to'] is not None and m['effective_to'] > today) for m in members) and current != desired:
        raise ValueError('This employee has scheduled group changes. Editing that schedule is not supported yet.')
    for m in members:
        if active(m,command.effective_from) and m['group_id'] not in desired:
            replaced['group_memberships'].append(m)
            updated.memberships.remove(next(row for row in updated.memberships if row['id']==m['id']))
            if m['effective_from'] < command.effective_from:
                inserts['group_memberships'].append({**m,'id':prefix+'_end_'+m['group_id'],'effective_to':command.effective_from,**metadata})
    for group_id in sorted(desired-current):
        inserts['group_memberships'].append({'id':prefix+'_group_'+group_id,'employment_id':job['employment_id'],
            'group_id':group_id,'effective_from':command.effective_from,'effective_to':job['effective_to'],**metadata})
    updated.memberships.extend(inserts['group_memberships'])
    # Validate reporting cycles at every known boundary, including future reporting changes.
    boundaries = {r[key] for rows in (updated.attributes,updated.jobs) for r in rows
                  for key in ('effective_from','effective_to') if r[key] is not None and r[key]>=command.effective_from}
    boundaries.add(command.effective_from)
    for day in boundaries:
        jobs = {j['employment_id']:j['employee_id'] for j in updated.jobs if active(j,day)}
        managers = {jobs[a['employment_id']]:a['manager_id'] for a in updated.attributes if a['employment_id'] in jobs and active(a,day)}
        for person in managers:
            seen = set()
            while person is not None:
                if person in seen:
                    raise ValueError('This manager selection would create a reporting cycle')
                seen.add(person)
                person = managers.get(person)
    override_replaced, override_inserts = [], []
    for fix in command.coverage_fixes:
        if not any(c['id']==fix.category_id and c['cardinality']=='exactly_one' for c in inputs.categories):
            raise ValueError('Inline manual assignments are only for required categories')
        override = OverrideCommand(request_id=uuid5(command.request_id,fix.category_id),employee_id=employee_id,
            category_id=fix.category_id,policy_id=fix.policy_id,action='set',effective_from=command.effective_from,
            effective_to=job['effective_to'],reason=fix.reason)
        _, old, new = plan_override(updated,override,today,validate_coverage=False)
        updated.overrides = [o for o in updated.overrides if o['id'] not in {r['id'] for r in old}] + new
        override_replaced.extend(old)
        override_inserts.extend(new)
    affected = {employee_id,command.manager_id}
    if prior:
        affected.add(prior['manager_id'])
    affected.discard(None)
    before, after, gaps = [], [], []
    for person_id in sorted(affected):
        before.extend(resolve_timeline(inputs,person_id)[0])
        intervals, missing = resolve_timeline(updated,person_id)
        after.extend(intervals)
        gaps.extend(missing)
    impact = EmployeeImpact(employee_id=employee_id,affected_employee_ids=sorted(affected),before=before,after=after,gaps=gaps)
    return EmployeePlan(impact,updated,inserts,replaced,override_replaced,override_inserts)


def save_employee(connection, command: EmployeeCommand, today: date) -> EmployeeImpact:
    # Caller acquires assignment_transaction() before we reload any inputs.
    plan = plan_employee(load_inputs(connection),command,today,options(connection))
    if plan.impact.gaps:
        raise ValueError('Required assignments are missing. Preview and choose a policy for each gap before saving.')
    for table, rows in plan.replaced.items():
        for row in rows:
            connection.execute(text(f"UPDATE {table} SET superseded_at=now(),superseded_by='taylor',superseded_reason=:reason WHERE id=:id"),
                               {'id':row['id'],'reason':command.reason})
    # Fixed, internal column lists; command data is always bound, never SQL syntax.
    columns = {
        'employees':'id,name,email', 'employments':'id,employee_id',
        'employment_versions':'id,employment_id,employee_id,effective_from,effective_to,created_by,change_reason',
        'employee_versions':'id,employment_id,country,state,department_id,employment_type,manager_id,effective_from,effective_to,created_by,change_reason',
        'group_memberships':'id,employment_id,group_id,effective_from,effective_to,created_by,change_reason',
    }
    for table, rows in plan.inserts.items():
        names = columns[table]
        for row in rows:
            connection.execute(text(f"INSERT INTO {table} ({names}) VALUES ({','.join(':'+c for c in names.split(','))})"),row)
    write_override_rows(connection,plan.override_replaced,plan.override_inserts,command.reason)
    reconcile(connection,plan.impact.affected_employee_ids,reason=command.reason)
    plan.impact.saved = True
    return plan.impact
