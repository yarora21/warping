import { useEffect, useState } from "react";
import { Assignments, RulesCatalog } from "./Assignments";
import {
  dateLabel,
  loadDirectory,
  type Person,
  type Category,
  type Settings,
} from "./api";

const countries: Record<string, string> = {
  US: "United States",
  GB: "United Kingdom",
  CA: "Canada",
  IN: "India",
  FR: "France",
  IT: "Italy",
};
const labels = {
  exactly_one: "Choose one",
  at_most_one: "Optional",
  many: "Multiple allowed",
};
const kind = {
  salaried: "Salaried employee",
  hourly: "Hourly employee",
  contractor: "Contractor",
};
const initials = (name: string) =>
  name
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("");
const location = (person: Person) =>
  [person.state, countries[person.country] ?? person.country]
    .filter(Boolean)
    .join(", ");

export default function App() {
  const [data, setData] = useState<[Settings, Person[], Category[]] | null>(
    null,
  );
  const [error, setError] = useState("");
  const [page, setPage] = useState<"people" | "policies" | "assignments">(
    "people",
  );
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("all");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setError("");
    loadDirectory()
      .then((result) => {
        if (active) setData(result);
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message);
      });
    return () => {
      active = false;
    };
  }, [attempt]);

  function navigate(next: "people" | "policies" | "assignments") {
    setPage(next);
    setSelected(null);
    setSearch("");
  }
  const people = data?.[1] ?? [];
  const categories = data?.[2] ?? [];
  const person = people.find((employee) => employee.id === selected);
  const filtered = people.filter(
    (employee) =>
      `${employee.name} ${employee.email} ${employee.department} ${location(employee)}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (department === "all" || employee.department === department),
  );

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            ✳
          </span>{" "}
          northstar<span className="brand-dot">.</span>
        </div>
        <div className="company-switch">
          <span className="company-icon">N</span>
          <div>
            Northstar Studio<small>Company workspace</small>
          </div>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          <button
            className={page === "people" ? "nav-item active" : "nav-item"}
            aria-current={page === "people" ? "page" : undefined}
            onClick={() => navigate("people")}
          >
            <span aria-hidden="true">♧</span> People{" "}
            <span className="nav-count">{people.length}</span>
          </button>
          <button
            className={page === "policies" ? "nav-item active" : "nav-item"}
            aria-current={page === "policies" ? "page" : undefined}
            onClick={() => navigate("policies")}
          >
            <span aria-hidden="true">▤</span> Policies
          </button>
          <button
            className={page === "assignments" ? "nav-item active" : "nav-item"}
            aria-current={page === "assignments" ? "page" : undefined}
            onClick={() => navigate("assignments")}
          >
            <span aria-hidden="true">✓</span> Assignments
          </button>
        </nav>
        <div className="sidebar-note">
          <span className="tiny-star" aria-hidden="true">
            ✳
          </span>
          <p>
            A little clarity.
            <br />A better workday.
          </p>
          <small>People & policy workspace</small>
        </div>
        <div className="user">
          <span className="avatar small">TB</span>
          <div>
            Taylor Brooks<small>HR admin · Demo</small>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>
            Workspace <span className="slash">/</span>{" "}
            {page === "people"
              ? "People"
              : page === "policies"
                ? "Policies"
                : "Assignments"}
            {person && (
              <>
                <span className="slash">/</span> {person.name}
              </>
            )}
          </span>
          <span className="demo-date">
            <span className="status-dot" /> Demo date{" "}
            <strong>{data ? dateLabel(data[0].today) : "Loading…"}</strong>
          </span>
        </header>
        <main id="main">
          {error ? (
            <div className="empty" role="alert">
              <h1>Let’s try that again</h1>
              <p>{error}</p>
              <button
                className="primary"
                onClick={() => setAttempt(attempt + 1)}
              >
                Reload data
              </button>
            </div>
          ) : !data ? (
            <div className="empty" role="status">
              Loading your workspace…
            </div>
          ) : person ? (
            <>
              <button className="back-link" onClick={() => setSelected(null)}>
                ← Back to people
              </button>
              <div className="profile-heading">
                <span className="avatar large">{initials(person.name)}</span>
                <div>
                  <div className="eyebrow">EMPLOYEE PROFILE</div>
                  <h1>{person.name}</h1>
                  <p>{person.email}</p>
                </div>
                <span className={`badge ${person.status}`}>
                  {person.status}
                </span>
              </div>
              <section className="panel profile-panel">
                <div className="panel-heading">
                  <h2>Employment details</h2>
                  <span className="muted">
                    As of {dateLabel(data[0].today)}
                  </span>
                </div>
                <dl className="details">
                  <div>
                    <dt>Department</dt>
                    <dd>{person.department}</dd>
                  </div>
                  <div>
                    <dt>Employment type</dt>
                    <dd>{kind[person.employment_type]}</dd>
                  </div>
                  <div>
                    <dt>Location</dt>
                    <dd>{location(person)}</dd>
                  </div>
                  <div>
                    <dt>Start date</dt>
                    <dd>{dateLabel(person.start_date)}</dd>
                  </div>
                  <div>
                    <dt>Reports to</dt>
                    <dd>
                      {person.manager_id ? (
                        <button
                          className="text-link"
                          onClick={() => setSelected(person.manager_id)}
                        >
                          {person.manager_name}
                        </button>
                      ) : (
                        "No manager"
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>
                      End date <span className="muted">(exclusive)</span>
                    </dt>
                    <dd>
                      {person.end_date ? dateLabel(person.end_date) : "Ongoing"}
                    </dd>
                  </div>
                  <div>
                    <dt>Groups</dt>
                    <dd>
                      {person.groups.length
                        ? person.groups.map((group) => (
                            <span className="pill" key={group}>
                              {group}
                            </span>
                          ))
                        : "No current groups"}
                    </dd>
                  </div>
                </dl>
              </section>
              <Assignments
                key={person.id}
                employeeId={person.id}
                people={people}
                categories={categories}
                today={data[0].today}
              />
            </>
          ) : page === "people" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">YOUR COMPANY, CONNECTED</div>
                  <h1>People</h1>
                  <p>A place for everyone. Get to know your team.</p>
                </div>
                <span className="subtle-tag">Directory preview</span>
              </div>
              <div className="stats">
                <div>
                  <span>People in your company</span>
                  <strong>
                    {people.length}
                    <small>across the team</small>
                  </strong>
                </div>
                <div>
                  <span>Active employees</span>
                  <strong>
                    {people.filter((p) => p.status === "active").length}
                    <small>working together</small>
                  </strong>
                </div>
                <div>
                  <span>Countries</span>
                  <strong>
                    {new Set(people.map((p) => p.country)).size}
                    <small>one shared workspace</small>
                  </strong>
                </div>
              </div>
              <section className="panel">
                <div className="toolbar">
                  <div className="section-title">
                    <h2>Employee directory</h2>
                    <span className="count">{filtered.length}</span>
                  </div>
                  <div className="filters">
                    <label className="search">
                      <span aria-hidden="true">⌕</span>
                      <input
                        aria-label="Search people"
                        placeholder="Search name, team, or location…"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                      />
                    </label>
                    <select
                      aria-label="Filter by department"
                      value={department}
                      onChange={(event) => setDepartment(event.target.value)}
                    >
                      <option value="all">All departments</option>
                      {[...new Set(people.map((p) => p.department))]
                        .sort()
                        .map((value) => (
                          <option key={value}>{value}</option>
                        ))}
                    </select>
                  </div>
                </div>
                {!filtered.length ? (
                  <div className="empty">
                    <h3>
                      {people.length
                        ? "No matching people"
                        : "Your directory is ready for people"}
                    </h3>
                    <p>
                      {people.length
                        ? "Try another name, location, or department."
                        : "Run the documented seed command to add the demo company."}
                    </p>
                    {people.length > 0 && (
                      <button
                        className="text-link"
                        onClick={() => {
                          setSearch("");
                          setDepartment("all");
                        }}
                      >
                        Clear filters
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Employee</th>
                          <th>Department</th>
                          <th>Location</th>
                          <th>Employment</th>
                          <th>Status</th>
                          <th>
                            <span className="sr-only">Open profile</span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((employee, index) => (
                          <tr key={employee.id}>
                            <td>
                              <button
                                className="person-link"
                                onClick={() => setSelected(employee.id)}
                              >
                                <span className={`avatar tone-${index % 4}`}>
                                  {initials(employee.name)}
                                </span>
                                <span>
                                  {employee.name}
                                  <small>{employee.email}</small>
                                </span>
                              </button>
                            </td>
                            <td>{employee.department}</td>
                            <td>{location(employee)}</td>
                            <td>{kind[employee.employment_type]}</td>
                            <td>
                              <span className={`badge ${employee.status}`}>
                                {employee.status}
                              </span>
                            </td>
                            <td>
                              <button
                                className="arrow-button"
                                aria-label={`View ${employee.name}`}
                                onClick={() => setSelected(employee.id)}
                              >
                                ↗
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="table-footer">
                  {filtered.length} of {people.length} people
                  <span>All employee information is fictional.</span>
                </div>
              </section>
            </>
          ) : page === "assignments" ? (
            <Assignments
              people={people}
              categories={categories}
              today={data[0].today}
            />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">A FOUNDATION FOR YOUR TEAM</div>
                  <h1>Policies</h1>
                  <p>
                    The benefits, tools, and schedules that support your people.
                  </p>
                </div>
                <span className="subtle-tag">
                  {categories.reduce(
                    (sum, category) => sum + category.policies.length,
                    0,
                  )}{" "}
                  policies
                </span>
              </div>
              <div className="catalog-intro">
                <span className="intro-mark" aria-hidden="true">
                  ✳
                </span>
                <div>
                  <h2>Clear policies. Confident decisions.</h2>
                  <p>
                    Explore your company’s policies and the rules that assign
                    them. Open Assignments to see who receives each policy.
                  </p>
                </div>
              </div>
              {!categories.length && (
                <div className="empty">
                  <h2>No policies yet</h2>
                  <p>Run the seed command to explore example categories.</p>
                </div>
              )}
              <RulesCatalog categories={categories} />
              {categories.map((category) => (
                <section className="category-section" key={category.id}>
                  <div className="category-title">
                    <h2>{category.name}</h2>
                    <span className="pill">{labels[category.cardinality]}</span>
                  </div>
                  <div className="policy-grid">
                    {category.policies.map((policy) => (
                      <article className="policy-card" key={policy.id}>
                        <span className="policy-icon" aria-hidden="true">
                          {category.id === "apps"
                            ? "⌘"
                            : category.id === "vacation"
                              ? "☀"
                              : "▤"}
                        </span>
                        <h3>{policy.name}</h3>
                        <p>{policy.description}</p>
                        <div className="policy-footer">
                          <span className="status-dot" /> Available in catalog
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              ))}
            </>
          )}
          <footer className="page-footer">
            Northstar Studio{" "}
            <span>
              Thoughtful policies start with understanding your people.
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}
