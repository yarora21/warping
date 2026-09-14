import { useEffect, useState } from "react";
import { Overrides } from "./Overrides";
import {
  dateLabel,
  get,
  queryAssignments,
  type Category,
  type Interval,
  type Person,
  type Report,
  type Rule,
} from "./api";

function valueLabel(value: unknown) {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return value == null ? "Not set" : String(value);
}

export function Why({ assignment }: { assignment: Interval }) {
  const explanation = assignment.explanation;
  const appliedRules = explanation.matched_rules.filter((rule) =>
    explanation.source_rule_version_ids.includes(rule.version_id),
  );
  const unusedRules = explanation.matched_rules.filter(
    (rule) => !explanation.source_rule_version_ids.includes(rule.version_id),
  );
  return (
    <details className="why">
      <summary>Why?</summary>
      <div className="explanation">
        <strong>
          {explanation.override
            ? `${explanation.policy_name} was assigned manually.`
            : `${explanation.policy_name} applies because:`}
        </strong>
        {explanation.override && (
          <p>
            {explanation.override.reason}
            <br />
            <small>
              {explanation.override.created_by === "taylor"
                ? "Taylor Brooks"
                : explanation.override.created_by}{" "}
              · {dateLabel(explanation.override.effective_from)} →{" "}
              {explanation.override.effective_to
                ? dateLabel(explanation.override.effective_to) + " (exclusive)"
                : "ongoing"}
            </small>
          </p>
        )}
        {appliedRules.map((rule) => (
          <div className="rule-evidence" key={rule.version_id}>
            {rule.facts.length ? (
              <ul>
                {rule.facts.map((fact, i) => (
                  <li key={i}>
                    {fact.field === "tenure_months"
                      ? `Length of service is ${fact.operator === "gte" ? "at least" : fact.operator === "lt" ? "less than" : "exactly"} ${valueLabel(fact.expected)} completed months.`
                      : fact.field === "is_manager"
                        ? fact.actual
                          ? "They manage employees."
                          : "They do not manage employees."
                        : `${fact.label}: ${valueLabel(fact.actual)}.`}
                  </li>
                ))}
              </ul>
            ) : (
              <p>This rule covers everyone in active employment.</p>
            )}
            <small className="muted">Assigned by “{rule.name}”.</small>
          </div>
        ))}
        {explanation.decision === "union" && (
          <p>
            This category allows multiple policies, so other matching policies
            can apply too.
          </p>
        )}
        {unusedRules.length > 0 && (
          <details>
            <summary>Why weren’t other matching rules used?</summary>
            <p>
              {explanation.override
                ? "The manual assignment replaces the automatic choice."
                : "Only one policy can be assigned in this category. When several rules match, the company’s rule order determines which one is used."}
            </p>
            <ul>
              {unusedRules.map((rule) => (
                <li key={rule.version_id}>
                  “{rule.name}” also matches, but{" "}
                  {explanation.override
                    ? "the manual assignment is used instead."
                    : `“${appliedRules[0]?.name}” is checked first.`}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </details>
  );
}

export function Assignments({
  people,
  categories,
  today,
  employeeId,
}: {
  people: Person[];
  categories: Category[];
  today: string;
  employeeId?: string;
}) {
  const [day, setDay] = useState(today);
  const [selected, setSelected] = useState<string[]>(
    employeeId ? [employeeId] : people.map((p) => p.id),
  );
  const [category, setCategory] = useState("");
  const [policy, setPolicy] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [timeline, setTimeline] = useState<Interval[]>([]);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const selectionKey = selected.join(",");
  useEffect(() => {
    let alive = true;
    setReport(null);
    setTimeline([]);
    setError("");
    if (!day) return;
    Promise.all([
      queryAssignments({
        as_of: day,
        employee_ids: selected,
        category_id: category || null,
        policy_id: policy || null,
      }),
      employeeId
        ? get<Interval[]>(`people/${employeeId}/timeline`)
        : Promise.resolve([]),
    ])
      .then(([result, intervals]) => {
        if (alive) {
          setReport(result);
          setTimeline(intervals);
        }
      })
      .catch((reason: Error) => {
        if (alive) setError(reason.message);
      });
    return () => {
      alive = false;
    };
  }, [day, selectionKey, category, policy, employeeId, attempt]);
  const names = Object.fromEntries(people.map((p) => [p.id, p.name]));
  const policies = categories
    .filter((c) => !category || c.id === category)
    .flatMap((c) => c.policies);
  return (
    <section className="assignment-section">
      {!employeeId && (
        <div className="page-heading">
          <div>
            <div className="eyebrow">CLEAR ANSWERS FOR YOUR TEAM</div>
            <h1>Assignments</h1>
            <p>Choose people and a date to see what applies, and why.</p>
          </div>
        </div>
      )}
      {employeeId && (
        <Overrides
          employeeId={employeeId}
          categories={categories}
          today={today}
          asOf={day || today}
          onSaved={() => setAttempt((n) => n + 1)}
        />
      )}
      <div className="panel">
        <div className="toolbar assignment-toolbar">
          <h2>{employeeId ? "Policy assignments" : "Assignment report"}</h2>
          <div className="filters">
            <label>
              As of{" "}
              <input
                aria-label="Assignments as of"
                type="date"
                value={day}
                onChange={(e) => setDay(e.target.value)}
              />
            </label>
            <select
              aria-label="Assignment category"
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setPolicy("");
              }}
            >
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <select
              aria-label="Assigned policy"
              value={policy}
              onChange={(e) => setPolicy(e.target.value)}
            >
              <option value="">All policies</option>
              {policies.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        {!employeeId && (
          <details className="employee-picker">
            <summary>
              {selected.length} of {people.length} people selected
            </summary>
            <div className="selection-actions">
              <button
                className="text-link"
                onClick={() => setSelected(people.map((p) => p.id))}
              >
                Select all
              </button>
              <button className="text-link" onClick={() => setSelected([])}>
                Clear selection
              </button>
            </div>
            <div className="employee-checkboxes">
              {people.map((p) => (
                <label key={p.id}>
                  <input
                    type="checkbox"
                    checked={selected.includes(p.id)}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selected, p.id]
                          : selected.filter((id) => id !== p.id),
                      )
                    }
                  />{" "}
                  {p.name}
                </label>
              ))}
            </div>
          </details>
        )}
        {day > today && (
          <p className="assignment-note">
            Future assignments reflect the rules and employee information
            recorded now.
          </p>
        )}
        {error ? (
          <div className="empty" role="alert">
            <p>{error}</p>
            <button onClick={() => setAttempt(attempt + 1)}>Try again</button>
          </div>
        ) : !day ? (
          <p className="assignment-note">Choose a date to view assignments.</p>
        ) : !report ? (
          <div className="empty" role="status">
            Loading assignments…
          </div>
        ) : (
          <>
            {report.gaps.map((g) => (
              <p
                className="coverage-error"
                role="alert"
                key={`${g.employee_id}-${g.category_id}`}
              >
                {names[g.employee_id]}: {g.message}
              </p>
            ))}
            {report.inactive_employee_ids.length > 0 && (
              <p className="assignment-note">
                Not employed on this date:{" "}
                {report.inactive_employee_ids.map((id) => names[id]).join(", ")}
                .
              </p>
            )}
            {!report.assignments.length ? (
              <div className="empty">
                {selected.length
                  ? "No assignments match this date and selection."
                  : "Select one or more people to view assignments."}
              </div>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      {!employeeId && <th>Employee</th>}
                      <th>Category</th>
                      <th>Policy</th>
                      <th>Source</th>
                      <th>Explanation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.assignments.map((a) => (
                      <tr
                        key={`${a.employee_id}-${a.category_id}-${a.policy_id}`}
                      >
                        {!employeeId && <td>{names[a.employee_id]}</td>}
                        <td>{a.explanation.category_name}</td>
                        <td>{a.explanation.policy_name}</td>
                        <td>
                          <span className="badge">
                            {a.explanation.override ? "Manual" : "Automatic"}
                          </span>
                        </td>
                        <td>
                          <Why assignment={a} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
      {employeeId && timeline.length > 0 && (
        <section className="panel timeline">
          <div className="panel-heading">
            <h2>Assignment timeline</h2>
            <span className="muted">End dates are exclusive</span>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Category / policy</th>
                  <th>From</th>
                  <th>Until</th>
                  <th>Explanation</th>
                </tr>
              </thead>
              <tbody>
                {timeline
                  .filter(
                    (a) =>
                      (!category || a.category_id === category) &&
                      (!policy || a.policy_id === policy),
                  )
                  .sort((a, b) =>
                    b.effective_from.localeCompare(a.effective_from),
                  )
                  .map((a, i) => (
                    <tr key={i}>
                      <td>
                        {a.explanation.category_name}
                        <br />
                        <strong>{a.explanation.policy_name}</strong>
                      </td>
                      <td>{dateLabel(a.effective_from)}</td>
                      <td>
                        {a.effective_to ? dateLabel(a.effective_to) : "Ongoing"}
                      </td>
                      <td>
                        <Why assignment={a} />
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </section>
  );
}

export function RulesCatalog({ categories }: { categories: Category[] }) {
  const [rules, setRules] = useState<Rule[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    get<Rule[]>("rules")
      .then((r) => {
        if (alive) setRules(r);
      })
      .catch(() => {
        if (alive) setError("Rules could not be loaded.");
      });
    return () => {
      alive = false;
    };
  }, []);
  const policies = Object.fromEntries(
    categories.flatMap((c) => c.policies).map((p) => [p.id, p.name]),
  );
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Assignment rules</h2>
        <span className="muted">Rules determine who receives each policy</span>
      </div>
      {error && <p role="alert">{error}</p>}
      {!rules && !error && <p className="assignment-note">Loading rules…</p>}
      {rules?.map((rule) => (
        <details className="rule-list-item" key={rule.id}>
          <summary>
            <strong>{rule.name}</strong> → {policies[rule.policy_id]}
          </summary>
          <p>
            From {dateLabel(rule.effective_from)}
            {rule.effective_to
              ? ` until ${dateLabel(rule.effective_to)} (exclusive)`
              : " onward"}
            .
          </p>
          <p>{rule.summary}</p>
        </details>
      ))}
    </section>
  );
}
