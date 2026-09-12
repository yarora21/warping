from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from app import clock, queries
from app.database import engine
from app.schemas import Category, Person, Settings

app = FastAPI(title="Northstar policy assignments", version="0.1.0")


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
