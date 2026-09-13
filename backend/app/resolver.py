"""Pure point/timeline resolution. No database, HTTP, or clock dependencies."""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator


@dataclass(frozen=True)
class FieldSpec:
    label: str
    kind: str
    operators: tuple[str, ...]
    dependencies: tuple[str, ...]

    def read(self, snapshot: dict, key: str):
        return snapshot[key]

    def boundaries(self, start: date, operator: str, value: Any) -> list[date]:
        if self.kind != 'tenure':
            return []  # All other fields change only at their stored input dates.
        months = [value, value + 1] if operator == 'equals' else [value]
        return [day for n in months if (day := anniversary(start, n)) is not None]


FIELDS = {
    'country': FieldSpec('Country', 'string', ('equals', 'in'), ('employee_versions',)),
    'state': FieldSpec('State / region', 'string', ('equals', 'in'), ('employee_versions',)),
    'department_id': FieldSpec('Department', 'string', ('equals', 'in'), ('employee_versions',)),
    'employment_type': FieldSpec('Employment type', 'string', ('equals', 'in'), ('employee_versions',)),
    'group_ids': FieldSpec('Member of any group', 'groups', ('in',), ('group_memberships',)),
    'tenure_months': FieldSpec('Completed months of service', 'tenure', ('equals', 'gte', 'lt'), ('employment_versions',)),
    'is_manager': FieldSpec('Has active direct reports', 'boolean', ('equals',), ('employment_versions', 'employee_versions')),
}


class Condition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: str
    operator: str
    value: StrictStr | StrictInt | StrictBool | list[StrictStr]

    @model_validator(mode='after')
    def valid_operand(self):
        spec = FIELDS.get(self.field)
        if spec is None or self.operator not in spec.operators:
            raise ValueError('Unsupported field or operator')
        valid = (type(self.value) is bool if spec.kind == 'boolean' else
                 type(self.value) is int and 0 <= self.value <= 1200 if spec.kind == 'tenure' else
                 isinstance(self.value, list) and bool(self.value) if self.operator == 'in' else
                 isinstance(self.value, str) and bool(self.value))
        if not valid:
            raise ValueError('Invalid condition value')
        if isinstance(self.value, list):
            self.value = sorted(set(self.value))
        return self


class Conditions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    all: list[Condition]


def describe_conditions(conditions: dict) -> str:
    operators = {'equals': 'is', 'in': 'includes any of', 'gte': 'is at least', 'lt': 'is less than'}
    parts = []
    for c in Conditions.model_validate(conditions).all:
        value = ', '.join(c.value) if isinstance(c.value, list) else str(c.value)
        if type(c.value) is bool:
            value = 'yes' if c.value else 'no'
        parts.append(f'{FIELDS[c.field].label} {operators[c.operator]} {value}')
    return ' AND '.join(parts) if parts else 'Everyone in active employment.'


class Fact(BaseModel):
    field: str
    label: str
    operator: str
    expected: str | int | bool | list[str]
    actual: str | int | bool | list[str] | None
    satisfied: bool


class RuleEvidence(BaseModel):
    rule_id: str
    version_id: str
    name: str
    policy_id: str
    priority: int
    facts: list[Fact]


class Explanation(BaseModel):
    schema_version: int = 1
    decision: Literal['priority', 'union', 'missing_required']
    category_name: str
    policy_name: str | None
    input_revision_ids: list[str]
    matched_rules: list[RuleEvidence]
    source_rule_version_ids: list[str]
    tie_broken: bool = False


class Assignment(BaseModel):
    employee_id: str
    category_id: str
    policy_id: str
    is_single: bool
    explanation: Explanation


class Gap(BaseModel):
    employee_id: str
    category_id: str
    message: str


class Resolution(BaseModel):
    assignments: list[Assignment] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)


class Interval(Assignment):
    effective_from: date
    effective_to: date | None = None


@dataclass
class Inputs:
    employees: list[dict]
    jobs: list[dict]
    attributes: list[dict]
    memberships: list[dict]
    categories: list[dict]
    policies: list[dict]
    rules: list[dict]


def active(row: dict, day: date) -> bool:
    return row['effective_from'] <= day and (row['effective_to'] is None or day < row['effective_to'])


def anniversary(start: date, months: int) -> date | None:
    year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
    return date(year, month + 1, min(start.day, monthrange(year, month + 1)[1])) if year <= 9999 else None


def snapshot(inputs: Inputs, employee_id: str, day: date) -> tuple[dict, list[str]] | None:
    jobs = [j for j in inputs.jobs if j['employee_id'] == employee_id and active(j, day)]
    if not jobs:
        return None
    if len(jobs) != 1:
        raise ValueError('Overlapping employments')
    job = jobs[0]
    attributes = [a for a in inputs.attributes if a['employment_id'] == job['employment_id'] and active(a, day)]
    if len(attributes) != 1:
        raise ValueError(f'Missing or overlapping attributes for {employee_id} on {day}')
    attr = attributes[0]
    memberships = [m for m in inputs.memberships if m['employment_id'] == job['employment_id'] and active(m, day)]
    active_jobs = {j['employment_id']: j for j in inputs.jobs if active(j, day)}
    reports = [a for a in inputs.attributes if a['manager_id'] == employee_id and active(a, day)
               and a['employment_id'] in active_jobs]
    start = job['effective_from']
    months = (day.year - start.year) * 12 + day.month - start.month
    if day < anniversary(start, months):
        months -= 1
    facts = {**attr, 'group_ids': sorted({m['group_id'] for m in memberships}),
             'tenure_months': months, 'is_manager': bool(reports)}
    ids = [job['id'], attr['id']] + [m['id'] for m in memberships]
    ids += [a['id'] for a in reports] + [active_jobs[a['employment_id']]['id'] for a in reports]
    return facts, sorted(set(ids))


def evaluate(condition: Condition, values: dict) -> Fact:
    spec = FIELDS[condition.field]
    actual = spec.read(values, condition.field)
    expected = condition.value
    if condition.operator == 'equals':
        satisfied = actual == expected
    elif condition.operator == 'in':
        satisfied = bool(set(actual) & set(expected)) if spec.kind == 'groups' else actual in expected
    elif condition.operator == 'gte':
        satisfied = actual >= expected
    else:
        satisfied = actual < expected
    # Tenure keeps changing; the predicate truth does not. Preserve a stable fact.
    shown = ('Threshold met' if satisfied else 'Threshold not met') if spec.kind == 'tenure' else actual
    return Fact(field=condition.field, label=spec.label, operator=condition.operator,
                expected=expected, actual=shown, satisfied=satisfied)


def resolve(inputs: Inputs, employee_ids: list[str], day: date) -> Resolution:
    result = Resolution()
    policies = {p['policy_id']: p for p in inputs.policies if active(p, day)}
    rules = sorted((r for r in inputs.rules if active(r, day) and r['policy_id'] in policies),
                   key=lambda r: (r['priority'], r['rule_id']))
    for employee_id in sorted(set(employee_ids)):
        loaded = snapshot(inputs, employee_id, day)
        if loaded is None:
            continue
        values, refs = loaded
        matches = []
        for rule in rules:
            conditions = Conditions.model_validate(rule['conditions']).all
            facts = sorted((evaluate(c, values) for c in conditions), key=lambda f: f.model_dump_json())
            if all(f.satisfied for f in facts):
                matches.append(RuleEvidence(rule_id=rule['rule_id'], version_id=rule['id'], name=rule['name'],
                                            policy_id=rule['policy_id'], priority=rule['priority'], facts=facts))
        for category in sorted(inputs.categories, key=lambda c: c['id']):
            matching = [r for r in matches if policies[r.policy_id]['category_id'] == category['id']]
            single = category['cardinality'] != 'many'
            if not matching and category['cardinality'] == 'exactly_one':
                result.gaps.append(Gap(employee_id=employee_id, category_id=category['id'],
                                       message=f"No {category['name']} matches. Add a rule or a manual assignment."))
            targets = [matching[0].policy_id] if matching and single else sorted({r.policy_id for r in matching})
            for target in targets:
                sources = [matching[0]] if single else [r for r in matching if r.policy_id == target]
                evidence = matching if single else sources
                policy = policies[target]
                result.assignments.append(Assignment(employee_id=employee_id, category_id=category['id'], policy_id=target,
                    is_single=single, explanation=Explanation(decision='priority' if single else 'union',
                        category_name=category['name'], policy_name=policy['name'],
                        input_revision_ids=sorted(set(refs + [policies[r.policy_id]['id'] for r in evidence])),
                        matched_rules=evidence, source_rule_version_ids=[r.version_id for r in sources],
                        tie_broken=single and len(matching) > 1 and matching[0].priority == matching[1].priority)))
    return result


def resolve_timeline(inputs: Inputs, employee_id: str) -> tuple[list[Interval], list[Gap]]:
    # Conservative company-wide boundaries keep cross-employee manager dependencies correct.
    boundaries = {r[key] for rows in (inputs.jobs, inputs.attributes, inputs.memberships, inputs.rules, inputs.policies)
                  for r in rows for key in ('effective_from', 'effective_to') if r[key] is not None}
    conditions = [c for r in inputs.rules for c in Conditions.model_validate(r['conditions']).all]
    for job in inputs.jobs:
        if job['employee_id'] == employee_id:
            for c in conditions:
                boundaries.update(FIELDS[c.field].boundaries(job['effective_from'], c.operator, c.value))
    dates = sorted(boundaries)
    intervals: list[Interval] = []
    previous: dict[tuple, Interval] = {}
    gaps: list[Gap] = []
    for i, start in enumerate(dates):
        end = dates[i + 1] if i + 1 < len(dates) else None
        resolved = resolve(inputs, [employee_id], start)
        gaps.extend(resolved.gaps)
        current = {}
        for assignment in resolved.assignments:
            key = (assignment.category_id, assignment.policy_id, assignment.explanation.model_dump_json())
            if key in previous and previous[key].effective_to == start:
                interval = previous[key]
                interval.effective_to = end
            else:
                interval = Interval(**assignment.model_dump(), effective_from=start, effective_to=end)
                intervals.append(interval)
            current[key] = interval
        previous = current
    return intervals, gaps
