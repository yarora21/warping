"""Explicit additive fixtures. Existing logical records are never overwritten."""
from calendar import monthrange
from datetime import timedelta
from sqlalchemy import text
from app.clock import today
from app.database import engine
from app.assignments import assignment_transaction, reconcile
import json


def months_before(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    return day.replace(year=year, month=month + 1, day=min(day.day, monthrange(year, month + 1)[1]))


def seed(connection):
    # Lock before fixture reads and writes; reconciliation shares this transaction.
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
        connection.execute(text("INSERT INTO assignment_categories (id,name,cardinality) VALUES (:id,:name,:cardinality) ON CONFLICT DO NOTHING"),
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

    rule_fixtures = [
        ('pay_default', 'Default monthly pay', 'monthly', 100, []),
        ('pay_us', 'US employee pay', 'biweekly', 10, [('country','equals','US'), ('employment_type','in',['salaried','hourly'])]),
        ('vacation_default', 'Standard vacation for everyone', 'standard', 100, []),
        ('vacation_tenure', 'Extended vacation after two years', 'extended', 10, [('tenure_months','gte',24)]),
        ('sick_us', 'US sick leave', 'sick_standard', 10, [('country','equals','US')]),
        ('slack_all', 'Slack for everyone', 'slack', 10, []),
        ('github_engineering', 'GitHub for Engineering', 'github', 10, [('department_id','equals','engineering')]),
        ('figma_design', 'Figma for Design', 'figma', 10, [('department_id','equals','design')]),
        ('figma_launch', 'Figma for the Launch team', 'figma', 20, [('group_ids','in',['launch'])]),
        ('security_all', 'Security training for everyone', 'security', 10, []),
        ('training_ca', 'California meal break training', 'ca_meal', 10, [('country','equals','US'),('state','equals','CA')]),
        ('training_manager', 'Training for people managers', 'manager', 10, [('is_manager','equals',True)]),
    ]
    for rule_id, name, policy, priority, clauses in rule_fixtures:
        added = connection.execute(text('INSERT INTO assignment_rules VALUES (:id) ON CONFLICT DO NOTHING RETURNING id'), {'id': rule_id}).scalar()
        if added:
            # Use the existing policy's start, not a fresh clock-relative seed date.
            connection.execute(text('''INSERT INTO assignment_rule_versions
                (id,rule_id,policy_id,name,priority,conditions,effective_from,created_by,change_reason)
                SELECT :id,:rule,:policy,:name,:priority,CAST(:conditions AS jsonb),min(effective_from),'taylor','Initial demo rule'
                FROM policy_versions WHERE policy_id=:policy'''),
                {'id': f'rule_{rule_id}_1', 'rule': rule_id, 'policy': policy, 'name': name, 'priority': priority,
                 'conditions': json.dumps({'all': [{'field': f, 'operator': op, 'value': value} for f, op, value in clauses]})})
    reconcile(connection, reason='Add missing demo fixtures')


if __name__ == "__main__":
    with assignment_transaction() as connection:
        seed(connection)
    print("Missing fixtures added and assignments reconciled. Existing input records were preserved.")
