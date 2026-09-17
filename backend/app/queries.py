"""Small, explicit read queries; no per-person query loops."""
from datetime import date
from sqlalchemy import text
from sqlalchemy.engine import Connection
from app.schemas import Category, Person


def people(connection: Connection, as_of: date) -> list[Person]:
    rows = connection.execute(text("""
        SELECT e.id, e.name, e.email, d.name AS department,
            v.employment_type, v.country, v.state, v.manager_id, m.name AS manager_name,
            job.effective_from AS start_date, job.effective_to AS end_date,
            CASE WHEN job.effective_from > :as_of THEN 'upcoming'
                 WHEN job.effective_to <= :as_of THEN 'former' ELSE 'active' END AS status,
            COALESCE((SELECT array_agg(g.name ORDER BY g.name)
                FROM group_memberships gm JOIN groups g ON g.id = gm.group_id
                WHERE gm.employment_id = job.employment_id AND gm.superseded_at IS NULL
                AND daterange(gm.effective_from, gm.effective_to, '[)') @>
                    GREATEST(job.effective_from, LEAST(CAST(:as_of AS date), COALESCE(job.effective_to - 1, CAST(:as_of AS date))))
            ), ARRAY[]::text[]) AS groups
        FROM employees e
        JOIN LATERAL (
            SELECT j.* FROM employment_versions j
            WHERE j.employee_id = e.id AND j.superseded_at IS NULL
            ORDER BY CASE WHEN daterange(j.effective_from, j.effective_to, '[)') @> CAST(:as_of AS date) THEN 0
                          WHEN j.effective_from > :as_of THEN 1 ELSE 2 END,
                     CASE WHEN j.effective_from > :as_of THEN j.effective_from END ASC,
                     j.effective_from DESC LIMIT 1
        ) job ON true
        JOIN LATERAL (
            SELECT a.* FROM employee_versions a
            WHERE a.employment_id = job.employment_id AND a.superseded_at IS NULL
            AND daterange(a.effective_from, a.effective_to, '[)') @>
                GREATEST(job.effective_from, LEAST(CAST(:as_of AS date), COALESCE(job.effective_to - 1, CAST(:as_of AS date))))
            LIMIT 1
        ) v ON true
        JOIN departments d ON d.id = v.department_id
        LEFT JOIN employees m ON m.id = v.manager_id
        ORDER BY e.name
    """), {"as_of": as_of}).mappings()
    return [Person.model_validate(dict(row)) for row in rows]


def catalog(connection: Connection, as_of: date) -> list[Category]:
    rows = connection.execute(text("""
        SELECT c.id, c.name, c.cardinality, p.id AS policy_id,
            v.name AS policy_name, v.description, v.effective_from
        FROM assignment_categories c
        LEFT JOIN policies p ON p.category_id = c.id
        LEFT JOIN policy_versions v ON v.policy_id = p.id AND v.superseded_at IS NULL
            AND daterange(v.effective_from, v.effective_to, '[)') @> CAST(:as_of AS date)
        ORDER BY c.id, v.name
    """), {"as_of": as_of}).mappings()
    result: dict[str, dict] = {}
    for row in rows:
        category = result.setdefault(row["id"], {"id": row["id"], "name": row["name"],
                                                "cardinality": row["cardinality"], "policies": []})
        if row["policy_name"]:
            category["policies"].append({"id": row["policy_id"], "name": row["policy_name"],
                                         "description": row["description"], "effective_from": row["effective_from"]})
    return [Category.model_validate(value) for value in result.values()]
