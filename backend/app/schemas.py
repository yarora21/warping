from datetime import date
from typing import Literal
from pydantic import BaseModel


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
