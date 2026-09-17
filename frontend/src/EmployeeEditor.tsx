import { useEffect, useState } from "react";
import { Why } from "./Assignments";
import {
  dateLabel,
  get,
  submitEmployee,
  type Category,
  type Person,
  type EmployeeCommand,
  type EmployeeFacts,
  type EmployeeImpact,
  type EmployeeOptions,
  type Interval,
} from "./api";

export function EmployeeEditor({
  person,
  people,
  categories,
  today,
  onSaved,
}: {
  person?: Person;
  people: Person[];
  categories: Category[];
  today: string;
  onSaved: () => void;
}) {
  const initial = (): EmployeeCommand => ({
    request_id: crypto.randomUUID(),
    employee_id: person?.id ?? null,
    ...(person ? {} : { name: "", email: "" }),
    effective_from:
      person && person.start_date > today ? person.start_date : today,
    country: "US",
    state: "",
    department_id: "",
    employment_type: "salaried",
    manager_id: null,
    group_ids: [],
    reason: "",
    coverage_fixes: [],
  });
  const [open, setOpen] = useState(false);
  const [command, setCommand] = useState<EmployeeCommand>(initial);
  const [choices, setChoices] = useState<EmployeeOptions | null>(null);
  const [impact, setImpact] = useState<EmployeeImpact | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [changed, setChanged] = useState(false);
  const [retry, setRetry] = useState(0);
  const [gapCategories, setGapCategories] = useState<string[]>([]);
  useEffect(() => {
    if (!open || !command.effective_from) return;
    let alive = true;
    setLoading(true);
    setLoadError("");
    Promise.all([
      get<EmployeeOptions>("employee-options"),
      person
        ? get<EmployeeFacts>(
            `people/${person.id}/edit?as_of=${command.effective_from}`,
          )
        : Promise.resolve(null),
    ])
      .then(([options, facts]) => {
        if (!alive) return;
        setChoices(options);
        if (facts) setCommand((c) => ({ ...c, ...facts }));
      })
      .catch((e: Error) => {
        if (alive) setLoadError(e.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [open, person?.id, command.effective_from, retry]);
  function update(values: Partial<EmployeeCommand>, keepGaps = false) {
    setCommand((c) => ({
      ...c,
      ...values,
      request_id: crypto.randomUUID(),
      ...(keepGaps ? {} : { coverage_fixes: [] }),
    }));
    setImpact(null);
    setError("");
    setChanged(false);
    if (!keepGaps) setGapCategories([]);
  }
  async function submit(preview: boolean) {
    setBusy(true);
    setError("");
    try {
      const result = await submitEmployee(command, preview);
      setChanged(
        !preview &&
          JSON.stringify(impact?.after) !== JSON.stringify(result.after),
      );
      setImpact(result);
      setGapCategories((ids) => [
        ...new Set([
          ...ids,
          ...result.gaps
            .filter((g) => g.employee_id === result.employee_id)
            .map((g) => g.category_id),
        ]),
      ]);
      if (result.saved) onSaved();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The change could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }
  function intervals(rows: Interval[], employeeId: string) {
    const visible = rows
      .filter(
        (i) =>
          i.employee_id === employeeId &&
          (!i.effective_to || i.effective_to > command.effective_from),
      )
      .sort(
        (a, b) =>
          a.category_id.localeCompare(b.category_id) ||
          a.effective_from.localeCompare(b.effective_from),
      );
    return visible.length ? (
      <ul>
        {visible.map((i, n) => (
          <li key={n}>
            <strong>{i.explanation.policy_name}</strong>{" "}
            <span className="pill">
              {i.explanation.override ? "Manual" : "Automatic"}
            </span>
            <div>
              <small>
                {dateLabel(
                  i.effective_from < command.effective_from
                    ? command.effective_from
                    : i.effective_from,
                )}{" "}
                →{" "}
                {i.effective_to
                  ? `${dateLabel(i.effective_to)} (exclusive)`
                  : "ongoing"}
              </small>
            </div>
            <Why assignment={i} />
          </li>
        ))}
      </ul>
    ) : (
      <p>No assignments.</p>
    );
  }
  return (
    <section className="panel employee-editor">
      <div className="panel-heading">
        <div>
          <h2>{person ? "Employee information" : "Grow your team"}</h2>
          <p className="muted">
            {person
              ? "Preview how an employee change affects their policies and managers."
              : "Add an employee and review their policies before saving."}
          </p>
        </div>
        <button
          className="primary"
          disabled={busy}
          onClick={() => {
            setCommand(initial());
            setOpen(true);
            setImpact(null);
            setError("");
            setGapCategories([]);
            setRetry((n) => n + 1);
          }}
        >
          {person ? "Edit employee" : "Add employee"}
        </button>
      </div>
      {open && (
        <form
          className="override-form"
          onSubmit={(e) => {
            e.preventDefault();
            void submit(true);
          }}
        >
          <h3>{person ? `Update ${person.name}` : "New employee"}</h3>
          <p>
            Changes start on the chosen date. Earlier assignments stay in
            history. Start dates and edits must be today or later.
          </p>
          <label className="employee-date">
            {person ? "Effective date" : "Employment start date"}
            <input
              type="date"
              required
              min={today}
              value={command.effective_from}
              disabled={busy || !!impact?.saved}
              onChange={(e) => update({ effective_from: e.target.value })}
            />
          </label>
          {person && (
            <p className="muted">
              Changing the date reloads the information recorded for that date.
            </p>
          )}
          {loading && <p role="status">Loading employee information…</p>}
          {loadError && (
            <p role="alert">
              {loadError}{" "}
              <button type="button" onClick={() => setRetry((n) => n + 1)}>
                Retry
              </button>
            </p>
          )}
          <fieldset
            disabled={
              busy ||
              loading ||
              !!loadError ||
              !!impact?.saved ||
              !command.effective_from
            }
          >
            {!person && (
              <>
                <label>
                  Full name
                  <input
                    required
                    maxLength={200}
                    value={command.name ?? ""}
                    onChange={(e) => update({ name: e.target.value })}
                  />
                </label>
                <label>
                  Email
                  <input
                    type="email"
                    required
                    maxLength={254}
                    value={command.email ?? ""}
                    onChange={(e) => update({ email: e.target.value })}
                  />
                </label>
              </>
            )}
            <label>
              Country code
              <input
                required
                pattern="[A-Z]{2}"
                maxLength={2}
                placeholder="US"
                value={command.country}
                onChange={(e) =>
                  update({ country: e.target.value.toUpperCase(), state: "" })
                }
              />
              <small>Two-letter code, such as US, GB, or IN.</small>
            </label>
            <label>
              State / region
              <input
                value={command.state ?? ""}
                placeholder="CA, NY, ON…"
                onChange={(e) =>
                  update({ state: e.target.value.toUpperCase() || null })
                }
              />
            </label>
            <label>
              Department
              <select
                required
                value={command.department_id}
                onChange={(e) => update({ department_id: e.target.value })}
              >
                <option value="">Choose department</option>
                {choices?.departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Employment type
              <select
                value={command.employment_type}
                onChange={(e) =>
                  update({
                    employment_type: e.target
                      .value as EmployeeCommand["employment_type"],
                  })
                }
              >
                <option value="salaried">Salaried employee</option>
                <option value="hourly">Hourly employee</option>
                <option value="contractor">Contractor</option>
              </select>
            </label>
            <label>
              Manager
              <select
                value={command.manager_id ?? ""}
                onChange={(e) => update({ manager_id: e.target.value || null })}
              >
                <option value="">No manager</option>
                {people
                  .filter(
                    (p) =>
                      p.id !== person?.id &&
                      p.start_date <= command.effective_from &&
                      (!p.end_date || p.end_date > command.effective_from),
                  )
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
              </select>
            </label>
            <div>
              <span>Groups</span>
              <div className="employee-group-options">
                {choices?.groups.map((g) => (
                  <label key={g.id}>
                    <input
                      type="checkbox"
                      checked={command.group_ids?.includes(g.id) ?? false}
                      onChange={(e) =>
                        update({
                          group_ids: e.target.checked
                            ? [...(command.group_ids ?? []), g.id]
                            : command.group_ids?.filter((id) => id !== g.id),
                        })
                      }
                    />
                    {g.name}
                  </label>
                ))}
              </div>
            </div>
            <label className="reason-field">
              Reason
              <textarea
                required
                maxLength={1000}
                placeholder={
                  person
                    ? "For example, relocating to California"
                    : "For example, new hire"
                }
                value={command.reason}
                onChange={(e) => update({ reason: e.target.value })}
              />
            </label>
            {gapCategories.map((id) => {
              const category = categories.find((c) => c.id === id);
              const fix = command.coverage_fixes?.find(
                (f) => f.category_id === id,
              );
              const updateFix = (values: {
                policy_id?: string;
                reason?: string;
              }) =>
                update(
                  {
                    coverage_fixes: [
                      ...(command.coverage_fixes ?? []).filter(
                        (f) => f.category_id !== id,
                      ),
                      {
                        category_id: id,
                        policy_id: fix?.policy_id ?? "",
                        reason: fix?.reason ?? "",
                        ...values,
                      },
                    ],
                  },
                  true,
                );
              return (
                <div className="coverage-fix reason-field" key={id}>
                  <h3>Choose {category?.name ?? "required policy"}</h3>
                  <p>
                    No automatic policy covers the full employment period. This
                    manual assignment will be saved with the employee change.
                  </p>
                  <label>
                    Policy
                    <select
                      required
                      value={fix?.policy_id ?? ""}
                      onChange={(e) => updateFix({ policy_id: e.target.value })}
                    >
                      <option value="">Choose policy</option>
                      {category?.policies.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Reason for manual assignment
                    <input
                      required
                      maxLength={1000}
                      value={fix?.reason ?? ""}
                      onChange={(e) => updateFix({ reason: e.target.value })}
                    />
                  </label>
                </div>
              );
            })}
          </fieldset>
          {error && (
            <p role="alert" className="coverage-error">
              {error}
            </p>
          )}
          {impact && (
            <div className="employee-impact">
              <h3>
                {impact.saved
                  ? "Saved assignment results"
                  : "Assignment preview"}
              </h3>
              <p>
                From {dateLabel(command.effective_from)} onward, including
                scheduled changes. Manual exceptions remain in effect.
              </p>
              {impact.gaps.length > 0 && (
                <p role="alert" className="coverage-error">
                  Required assignments are missing. Choose the policies above
                  and preview again.{" "}
                  {impact.gaps
                    .filter((g) => g.employee_id !== impact.employee_id)
                    .map(
                      (g) =>
                        `${people.find((p) => p.id === g.employee_id)?.name}: ${g.message}`,
                    )
                    .join(" ")}
                </p>
              )}
              {impact.affected_employee_ids.map((id) => (
                <details key={id} open={id === impact.employee_id}>
                  <summary>
                    {id === impact.employee_id
                      ? (person?.name ?? command.name)
                      : `${people.find((p) => p.id === id)?.name ?? "Manager"} · affected manager`}
                  </summary>
                  <div className="impact-preview">
                    <div>
                      <h3>Before</h3>
                      {intervals(impact.before, id)}
                    </div>
                    <div>
                      <h3>{impact.saved ? "Saved" : "After"}</h3>
                      {intervals(impact.after, id)}
                    </div>
                  </div>
                </details>
              ))}
            </div>
          )}
          {impact?.saved && (
            <p role="status" className="assignment-note">
              Saved. The directory and assignments are up to date.
              {changed &&
                " Inputs changed since preview; the actual saved results are shown above."}
            </p>
          )}
          <div className="override-actions">
            {!impact?.saved && (
              <button
                className="primary"
                disabled={
                  busy || loading || !!loadError || !command.effective_from
                }
                type="submit"
              >
                {busy ? "Working…" : "Preview assignments"}
              </button>
            )}
            {impact && !impact.saved && !impact.gaps.length && (
              <button
                className="primary"
                type="button"
                disabled={busy}
                onClick={() => void submit(false)}
              >
                {person ? "Save employee change" : "Add employee"}
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => setOpen(false)}
            >
              {impact?.saved ? "Done" : "Cancel"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
