from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from app import clock, queries
from app.database import engine
from app.schemas import Category, Person, Settings
from app.schemas import AssignmentQuery, AssignmentReport, RuleView
from app.assignments import load_inputs, stored_intervals, assignment_transaction
from app.overrides import OverrideCommand, OverrideImpact, OverrideView, plan_override, save_override
from sqlalchemy.exc import IntegrityError
from app.resolver import Interval, Gap, active, describe_conditions

app = FastAPI(title="Northstar policy assignments", version="0.1.0")


@app.get('/api/people/{employee_id}/overrides', response_model=list[OverrideView])
def employee_overrides(employee_id: str):
    with engine.connect() as connection:
        return connection.execute(text('''SELECT o.* FROM employee_assignment_overrides o
            JOIN employments e ON e.id=o.employment_id WHERE e.employee_id=:id AND o.superseded_at IS NULL
            ORDER BY o.effective_from,o.id'''), {'id':employee_id}).mappings().all()


@app.post('/api/overrides/preview', response_model=OverrideImpact)
def preview_override(command: OverrideCommand):
    try:
        with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
            return plan_override(load_inputs(connection),command,clock.today())[0]
    except ValueError as error:
        raise HTTPException(422,str(error)) from error


@app.post('/api/overrides', response_model=OverrideImpact)
def create_override(command: OverrideCommand):
    try:
        with assignment_transaction() as connection:
            return save_override(connection,command,clock.today())
    except ValueError as error:
        raise HTTPException(422,str(error)) from error
    except IntegrityError as error:
        raise HTTPException(409,'This change conflicts with another saved override. Refresh and try again.') from error


@app.post('/api/assignments/query', response_model=AssignmentReport)
def assignment_report(query: AssignmentQuery):
    # Read-only POST supports arbitrary explicit employee selections without URL limits.
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        inputs = load_inputs(connection)
        known = {e['id'] for e in inputs.employees}
        ids = set(query.employee_ids) if query.employee_ids is not None else known
        if ids - known:
            raise HTTPException(422, 'Unknown employee selection')
        assignments = [interval for _, interval in stored_intervals(connection, sorted(ids))
                       if interval.effective_from <= query.as_of and
                       (interval.effective_to is None or query.as_of < interval.effective_to)]
        employed = {j['employee_id'] for j in inputs.jobs if active(j, query.as_of)} & ids
        present = {(a.employee_id, a.category_id) for a in assignments}
        gaps = [Gap(employee_id=e, category_id=c['id'], message=f"No {c['name']} assigned. Run reconciliation or add a matching rule.")
                for e in sorted(employed) for c in inputs.categories if c['cardinality'] == 'exactly_one'
                and (e,c['id']) not in present and (query.category_id is None or query.category_id == c['id'])]
        filtered = [a for a in assignments if (query.category_id is None or a.category_id == query.category_id)
                    and (query.policy_id is None or a.policy_id == query.policy_id)]
        return AssignmentReport(as_of=query.as_of, assignments=filtered, gaps=gaps,
                                inactive_employee_ids=sorted(ids-employed))


@app.get('/api/people/{employee_id}/timeline', response_model=list[Interval])
def timeline(employee_id: str):
    with engine.connect() as connection:
        if not connection.execute(text('SELECT 1 FROM employees WHERE id=:id'), {'id': employee_id}).scalar():
            raise HTTPException(404, 'Employee not found')
        return [interval for _, interval in stored_intervals(connection, [employee_id])]


@app.get('/api/rules', response_model=list[RuleView])
def rules():
    with engine.connect() as connection:
        rows = connection.execute(text('''SELECT * FROM assignment_rule_versions WHERE superseded_at IS NULL
            ORDER BY priority, rule_id, effective_from''')).mappings().all()
        return [{**row, 'summary': describe_conditions(row['conditions'])} for row in rows]


@app.get("/api/health")
def health() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/settings", response_model=Settings)
def settings():
    return Settings(today=clock.today(), timezone=clock.timezone())


@app.get("/api/people", response_model=list[Person])
def people():
    with engine.connect() as connection:
        return queries.people(connection, clock.today())


@app.get("/api/people/{employee_id}", response_model=Person)
def person(employee_id: str):
    with engine.connect() as connection:
        match = next((person for person in queries.people(connection, clock.today()) if person.id == employee_id), None)
    if match is None:
        raise HTTPException(404, "Employee not found")
    return match


@app.get("/api/categories", response_model=list[Category])
def categories():
    with engine.connect() as connection:
        return queries.catalog(connection, clock.today())
