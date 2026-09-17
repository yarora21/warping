import { useEffect, useState } from "react";
import {
  dateLabel,
  get,
  submitOverride,
  type Category,
  type Interval,
  type OverrideCommand,
  type OverrideImpact,
  type OverrideView,
} from "./api";

export function Overrides({
  employeeId,
  categories,
  today,
  asOf,
  onSaved,
}: {
  employeeId: string;
  categories: Category[];
  today: string;
  asOf: string;
  onSaved: () => void;
}) {
  const defaultCategory =
    categories.find((c) => c.id === "pay") ?? categories[0];
  const initial = (): OverrideCommand => ({
    request_id: crypto.randomUUID(),
    employee_id: employeeId,
    category_id: defaultCategory?.id ?? "",
    policy_id: null,
    action: defaultCategory?.cardinality === "many" ? "add" : "set",
    effective_from: asOf > today ? asOf : today,
    effective_to: null,
    reason: "",
    target_override_id: null,
  });
  const [command, setCommand] = useState<OverrideCommand>(initial);
  const [open, setOpen] = useState(false);
  const [overrides, setOverrides] = useState<OverrideView[]>([]);
  const [impact, setImpact] = useState<OverrideImpact | null>(null);
  const [error, setError] = useState("");
  const [listError, setListError] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [changed, setChanged] = useState(false);
  useEffect(() => {
    let alive = true;
    setListError("");
    get<OverrideView[]>(`people/${employeeId}/overrides`)
      .then((rows) => {
        if (alive) setOverrides(rows);
      })
      .catch(() => {
        if (alive) setListError("Manual exceptions could not be loaded.");
      });
    return () => {
      alive = false;
    };
  }, [employeeId, refresh]);
  function update(values: Partial<OverrideCommand>) {
    setCommand({ ...command, ...values, request_id: crypto.randomUUID() });
    setImpact(null);
    setError("");
    setChanged(false);
  }
  const selectedCategory = categories.find((c) => c.id === command.category_id);
  const names = Object.fromEntries(
    categories.flatMap((c) => c.policies).map((p) => [p.id, p.name]),
  );
  const categoryNames = Object.fromEntries(
    categories.map((c) => [c.id, c.name]),
  );
  async function submit(preview: boolean) {
    setBusy(true);
    setError("");
    try {
      const result = await submitOverride(command, preview);
      setChanged(
        !preview &&
          JSON.stringify(impact?.after) !== JSON.stringify(result.after),
      );
      setImpact(result);
      if (!preview) {
        setRefresh((n) => n + 1);
        onSaved();
      }
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "This change could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }
  function useAutomatic(override: OverrideView) {
    setCommand({
      ...initial(),
      category_id: override.category_id,
      action: "end",
      target_override_id: override.id,
    });
    setImpact(null);
    setError("");
    setOpen(true);
    setChanged(false);
  }
  function rows(intervals: Interval[]) {
    const visible = intervals.filter(
      (i) => i.effective_to == null || i.effective_to > command.effective_from,
    );
    return visible.length ? (
      <ul>
        {visible.map((i, index) => (
          <li key={index}>
            <strong>{i.explanation.policy_name}</strong> ·{" "}
            {i.explanation.override ? "Manual" : "Automatic"}
            <br />
            <small>
              {dateLabel(
                i.effective_from < command.effective_from
                  ? command.effective_from
                  : i.effective_from,
              )}{" "}
              →{" "}
              {i.effective_to
                ? dateLabel(i.effective_to) + " (exclusive)"
                : "ongoing"}
            </small>
          </li>
        ))}
      </ul>
    ) : (
      <p>No assignment in this category.</p>
    );
  }
  return (
    <section className="panel override-panel">
      <div className="panel-heading">
        <h2>Manual exceptions</h2>
        <button
          className="text-link"
          disabled={busy}
          onClick={() => {
            setCommand(initial());
            setImpact(null);
            setError("");
            setOpen(true);
          }}
        >
          Change assignment
        </button>
      </div>
      {listError && (
        <p role="alert" className="coverage-error">
          {listError}{" "}
          <button onClick={() => setRefresh((n) => n + 1)}>Retry</button>
        </p>
      )}
      {!overrides.length && !listError && (
        <p className="assignment-note">
          Assignments follow company rules. Add an exception when someone needs
          a different policy.
        </p>
      )}
      {overrides.map((o) => (
        <div className="override-item" key={o.id}>
          <div>
            <strong>
              {categoryNames[o.category_id]}:{" "}
              {o.action === "clear"
                ? "Left unassigned"
                : o.action === "exclude"
                  ? `Excluded ${names[o.policy_id!]}`
                  : names[o.policy_id!]}
            </strong>
            <span className="pill">
              {o.effective_from > asOf
                ? "Scheduled"
                : o.effective_to && o.effective_to <= asOf
                  ? "Ended"
                  : "Manual"}
            </span>
            <p>{o.reason}</p>
            <small>
              {o.created_by === "taylor" ? "Taylor Brooks" : o.created_by} ·{" "}
              {dateLabel(o.effective_from)} →{" "}
              {o.effective_to
                ? dateLabel(o.effective_to) + " (exclusive)"
                : "ongoing"}
            </small>
          </div>
          {o.effective_from <= (asOf > today ? asOf : today) &&
            (!o.effective_to ||
              o.effective_to > (asOf > today ? asOf : today)) && (
              <button
                className="text-link"
                disabled={busy}
                onClick={() => useAutomatic(o)}
              >
                Use automatic assignment
              </button>
            )}
        </div>
      ))}
      {open && (
        <form
          className="override-form"
          onSubmit={(e) => {
            e.preventDefault();
            void submit(true);
          }}
        >
          <h3>
            {command.action === "end"
              ? "Return to automatic assignment"
              : "Change this employee’s assignment"}
          </h3>
          <fieldset disabled={busy}>
            <label>
              Category
              <select
                value={command.category_id}
                disabled={command.action === "end"}
                onChange={(e) => {
                  const c = categories.find((c) => c.id === e.target.value)!;
                  update({
                    category_id: c.id,
                    policy_id: null,
                    action: c.cardinality === "many" ? "add" : "set",
                  });
                }}
              >
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            {command.action !== "end" && (
              <label>
                Action
                <select
                  value={command.action}
                  onChange={(e) =>
                    update({
                      action: e.target.value as OverrideCommand["action"],
                      policy_id: null,
                    })
                  }
                >
                  {selectedCategory?.cardinality === "many" ? (
                    <>
                      <option value="add">Add policy</option>
                      <option value="exclude">Exclude policy</option>
                    </>
                  ) : (
                    <>
                      <option value="set">Select policy</option>
                      {selectedCategory?.cardinality === "at_most_one" && (
                        <option value="clear">Leave unassigned</option>
                      )}
                    </>
                  )}
                </select>
              </label>
            )}
            {!["clear", "end"].includes(command.action) && (
              <label>
                Policy
                <select
                  required
                  value={command.policy_id ?? ""}
                  onChange={(e) => update({ policy_id: e.target.value })}
                >
                  <option value="">Choose a policy</option>
                  {selectedCategory?.policies.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              Effective date
              <input
                type="date"
                required
                min={today}
                value={command.effective_from}
                onChange={(e) => update({ effective_from: e.target.value })}
              />
            </label>
            {command.action !== "end" && (
              <label>
                End date (optional, exclusive)
                <input
                  type="date"
                  min={command.effective_from}
                  value={command.effective_to ?? ""}
                  onChange={(e) =>
                    update({ effective_to: e.target.value || null })
                  }
                />
              </label>
            )}
            <label className="reason-field">
              Reason
              <textarea
                required
                maxLength={1000}
                value={command.reason}
                onChange={(e) => update({ reason: e.target.value })}
                placeholder="Why does this employee need an exception?"
              />
            </label>
          </fieldset>
          {error && (
            <p role="alert" className="coverage-error">
              {error}
            </p>
          )}
          {impact && (
            <div className="impact-preview">
              <div>
                <h3>Before</h3>
                {rows(impact.before)}
              </div>
              <div>
                <h3>{impact.saved ? "Saved result" : "After"}</h3>
                {rows(impact.after)}
              </div>
            </div>
          )}
          {impact?.saved && (
            <p role="status" className="assignment-note">
              Saved. Assignments and timelines are up to date.
              {changed &&
                " Inputs changed since the preview; the actual saved result is shown above."}
            </p>
          )}
          <div className="override-actions">
            {!impact?.saved && (
              <button className="primary" type="submit" disabled={busy}>
                {busy ? "Working…" : "Preview change"}
              </button>
            )}
            {impact && !impact.saved && (
              <button
                className="primary"
                type="button"
                disabled={busy}
                onClick={() => void submit(false)}
              >
                Save change
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
