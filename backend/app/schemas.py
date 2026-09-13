from datetime import date
from typing import Literal
from pydantic import BaseModel
from app.resolver import Interval, Gap, Conditions


class Settings(BaseModel):
    today: date
    timezone: str
    company: str = "Northstar"
    actor: str = "Taylor Brooks · HR admin"


class Person(BaseModel):
    id: str
    name: str
    email: str
    status: Literal["active", "upcoming", "former"]
    department: str
    employment_type: Literal["salaried", "hourly", "contractor"]
    country: str
    state: str | None
    start_date: date
    end_date: date | None
    manager_id: str | None
    manager_name: str | None
    groups: list[str]


class Policy(BaseModel):
    id: str
    name: str
    description: str
    effective_from: date


class Category(BaseModel):
    id: str
    name: str
    cardinality: Literal["exactly_one", "at_most_one", "many"]
    policies: list[Policy]


class AssignmentQuery(BaseModel):
    as_of: date
    employee_ids: list[str] | None = None
    category_id: str | None = None
    policy_id: str | None = None


class AssignmentReport(BaseModel):
    as_of: date
    assignments: list[Interval]
    gaps: list[Gap]
    inactive_employee_ids: list[str]


class RuleView(BaseModel):
    id: str
    rule_id: str
    name: str
    policy_id: str
    priority: int
    conditions: Conditions
    summary: str
    effective_from: date
    effective_to: date | None
