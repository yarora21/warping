"""Explicit additive fixtures. Existing logical records are never overwritten."""
from calendar import monthrange
from datetime import timedelta
from sqlalchemy import text
from app.clock import today
from app.database import engine


def months_before(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    return day.replace(year=year, month=month + 1, day=min(day.day, monthrange(year, month + 1)[1]))


def seed(connection):
    # Shared company lock; PR 2 adds reconciliation before this transaction commits.
    connection.execute(text("SELECT pg_advisory_xact_lock(72021001)"))
    reference = today()
    departments = [("engineering", "Engineering"), ("people", "People"), ("operations", "Operations"),
                   ("design", "Design"), ("sales", "Sales")]
    for key, name in departments:
        connection.execute(text("INSERT INTO departments VALUES (:id, :name) ON CONFLICT DO NOTHING"), {"id": key, "name": name})
    connection.execute(text("INSERT INTO groups VALUES ('launch', 'Launch team') ON CONFLICT DO NOTHING"))
    fixtures = [
        ("alex", "Alex Chen", "engineering", "US", "NY", "salaried", None),
        ("sam", "Sam Rivera", "operations", "US", "CA", "salaried", None),
        ("taylor", "Taylor Brooks", "people", "US", "NY", "salaried", None),
        ("jamie", "Jamie Park", "engineering", "US", "NY", "salaried", "alex"),
        ("morgan", "Morgan Ellis", "design", "US", "CA", "salaried", "alex"),
        ("priya", "Priya Shah", "engineering", "IN", None, "contractor", "alex"),
        ("oliver", "Oliver James", "sales", "GB", None, "salaried", "sam"),
        ("sofia", "Sofia Garcia", "operations", "US", "CA", "hourly", "sam"),
        ("noah", "Noah Williams", "engineering", "CA", "ON", "salaried", "alex"),
        ("amara", "Amara Okafor", "people", "GB", None, "salaried", "taylor"),
        ("leo", "Leo Martin", "design", "FR", None, "contractor", "alex"),
        ("maya", "Maya Patel", "sales", "US", "TX", "salaried", "sam"),
        ("ethan", "Ethan Kim", "engineering", "US", "WA", "salaried", "alex"),
        ("ava", "Ava Thompson", "operations", "US", "NY", "hourly", "sam"),
        ("luca", "Luca Rossi", "design", "IT", None, "contractor", "alex"),
        ("zoe", "Zoe Johnson", "people", "US", "CA", "salaried", "taylor"),
        ("riley", "Riley Davis", "engineering", "US", "NY", "salaried", "alex"),
        ("ben", "Ben Wilson", "sales", "US", "TX", "salaried", "sam"),
    ]
    # Insert identities first so managers can be referenced in any fixture order.
    for key, name, *_ in fixtures:
        connection.execute(text("INSERT INTO employees VALUES (:id,:name,:email) ON CONFLICT DO NOTHING"),
                           {"id": key, "name": name, "email": f"{key}@northstar.example"})
    for index, (key, name, department, country, state, kind, manager) in enumerate(fixtures):
        job_id = f"job_{key}"
        added = connection.execute(text("INSERT INTO employments VALUES (:id,:employee) ON CONFLICT DO NOTHING RETURNING id"),
                                   {"id": job_id, "employee": key}).scalar()
        if not added:
            continue
        start = months_before(reference, 36 + index)
        end = None
        if key == "morgan":
            start = months_before(reference + timedelta(days=18), 24)
        elif key == "riley":
            start = reference + timedelta(days=14)
        elif key == "ben":
            end = reference - timedelta(days=30)
        params = {"id": f"employment_{key}_1", "job": job_id, "employee": key,
                  "start": start, "end": end}
        connection.execute(text("""INSERT INTO employment_versions
            (id,employment_id,employee_id,effective_from,effective_to,created_by,change_reason)
            VALUES (:id,:job,:employee,:start,:end,'taylor','Initial demo employment')"""), params)
        connection.execute(text("""INSERT INTO employee_versions
            (id,employment_id,employment_type,country,state,department_id,manager_id,effective_from,effective_to,created_by,change_reason)
            VALUES (:id,:job,:kind,:country,:state,:department,:manager,:start,:end,'taylor','Initial demo attributes')"""),
            {**params, "id": f"attributes_{key}_1", "kind": kind, "country": country, "state": state,
             "department": department, "manager": manager})
    for key in ("jamie", "morgan", "sofia"):
        connection.execute(text("""INSERT INTO group_memberships
            (id,employment_id,group_id,effective_from,created_by,change_reason)
            SELECT :id, :job, 'launch', effective_from, 'taylor', 'Initial launch team'
            FROM employment_versions j WHERE j.employment_id = :job AND j.superseded_at IS NULL
            AND NOT EXISTS (SELECT 1 FROM group_memberships gm WHERE gm.employment_id = :job AND gm.group_id = 'launch')
            ON CONFLICT DO NOTHING"""), {"id": f"membership_{key}", "job": f"job_{key}"})
    catalog = [
        ("pay", "Pay schedule", "exactly_one", [
            ("monthly", "Monthly pay", "One predictable payment each month for global employees and contractors."),
            ("biweekly", "Biweekly pay", "A regular pay schedule with a payment every two weeks.")]),
        ("vacation", "Vacation", "exactly_one", [
            ("standard", "Standard vacation", "20 days of annual leave to rest, recharge, and explore."),
            ("extended", "Extended vacation", "25 days of annual leave for employees with two years of service.")]),
        ("sick", "Sick leave", "at_most_one", [("sick_standard", "Standard sick leave", "Dedicated time to take care of your health.")]),
        ("apps", "Application access", "many", [
            ("slack", "Slack", "Stay connected with your teammates across the company."),
            ("github", "GitHub", "Collaborate on code and review changes with Engineering."),
            ("figma", "Figma", "Design and share ideas with your project team.")]),
        ("training", "Compliance training", "many", [
            ("security", "Security essentials", "Learn how to protect company information and work securely."),
            ("ca_meal", "California meal breaks", "Understand meal and rest break expectations in California."),
            ("manager", "Manager essentials", "Build a respectful, supportive workplace for your direct reports.")]),
    ]
    for key, name, cardinality, policies in catalog:
        connection.execute(text("INSERT INTO assignment_categories VALUES (:id,:name,:cardinality) ON CONFLICT DO NOTHING"),
                           {"id": key, "name": name, "cardinality": cardinality})
        for policy_id, title, description in policies:
            added = connection.execute(text("INSERT INTO policies VALUES (:id,:category) ON CONFLICT DO NOTHING RETURNING id"),
                                       {"id": policy_id, "category": key}).scalar()
            if added:
                connection.execute(text("""INSERT INTO policy_versions
                    (id,policy_id,name,description,effective_from,created_by,change_reason)
                    VALUES (:version,:id,:name,:description,:start,'taylor','Initial policy catalog')"""),
                    {"version": f"policy_{policy_id}_1", "id": policy_id, "name": title,
                     "description": description, "start": months_before(reference, 120)})


if __name__ == "__main__":
    with engine.begin() as connection:
        seed(connection)
    print("Demo fixtures added. Existing records were preserved. PR 1: assignment calculation is not enabled yet.")
