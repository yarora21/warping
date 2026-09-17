"""Effective employee milestones derived from existing revisions, not a second event log."""
from datetime import date, timedelta
from pydantic import BaseModel
from app.assignments import load_inputs
from app.employees import options
from app.resolver import active


class HistoryChange(BaseModel):
    field: str
    before: str | None
    after: str | None


class HistoryReason(BaseModel):
    actor: str
    reason: str


class EmployeeEvent(BaseModel):
    id: str
    effective_date: date
    title: str
    changes: list[HistoryChange]
    reasons: list[HistoryReason]


def employee_history(connection, employee_id: str) -> list[EmployeeEvent]:
    inputs = load_inputs(connection)
    if not any(e['id']==employee_id for e in inputs.employees):
        raise ValueError('Employee not found')
    catalogs = options(connection)
    departments = {d.id:d.name for d in catalogs.departments}
    groups = {g.id:g.name for g in catalogs.groups}
    people = {e['id']:e['name'] for e in inputs.employees}
    kinds = {'salaried':'Salaried employee','hourly':'Hourly employee','contractor':'Contractor'}
    events = []
    for job in inputs.jobs:
        if job['employee_id']!=employee_id:
            continue
        attributes = [a for a in inputs.attributes if a['employment_id']==job['employment_id']]
        memberships = [m for m in inputs.memberships if m['employment_id']==job['employment_id']]

        def facts(day):
            if not active(job,day):
                return {}
            attr = next((a for a in attributes if active(a,day)),None)
            if attr is None:
                return {}
            return {'Location':', '.join(v for v in (attr['state'],attr['country']) if v),
                    'Department':departments.get(attr['department_id'],attr['department_id']),
                    'Manager':people.get(attr['manager_id'],'No manager'),
                    'Employment type':kinds[attr['employment_type']],
                    'Groups':', '.join(sorted(groups[m['group_id']] for m in memberships if active(m,day))) or 'No groups'}

        dates = {job['effective_from']} | {d for row in attributes+memberships for d in (row['effective_from'],row['effective_to'])
                   if d is not None and active(job,d)}
        if job['effective_to']:
            dates.add(job['effective_to'])
        for day in sorted(dates):
            before = facts(day-timedelta(days=1)) if day>date.min else {}
            after = facts(day)
            hired = day==job['effective_from']
            ended = day==job['effective_to']
            changes = [HistoryChange(field=field,before=before.get(field),after=after.get(field))
                       for field in dict.fromkeys([*before,*after]) if before.get(field)!=after.get(field)]
            if not changes and not hired and not ended:
                continue  # Ignore revision boundaries that did not change employee information.
            titles = {'Location':'Relocated','Department':'Department changed','Manager':'Manager changed',
                      'Employment type':'Employment type changed','Groups':'Groups changed'}
            title = 'Hired' if hired else 'Employment ended' if ended else ' · '.join(titles[c.field] for c in changes)
            sources = [job] if hired or ended else [a for a in attributes if a['effective_from']==day]
            if not hired and not ended and any(c.field=='Groups' for c in changes):
                sources += [m for m in memberships if day in (m['effective_from'],m['effective_to'])]
            reasons = sorted({(people.get(r['created_by'],r['created_by']),r['change_reason']) for r in sources})
            events.append(EmployeeEvent(id=f"{job['employment_id']}:{day}",effective_date=day,title=title,changes=changes,
                reasons=[HistoryReason(actor=actor,reason=reason) for actor,reason in reasons]))
    return sorted(events,key=lambda e:(e.effective_date,e.id),reverse=True)
