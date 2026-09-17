import { useEffect, useState } from "react";
import {
  dateLabel,
  get,
  post,
  type Category,
  type Person,
  type Rule,
  type RuleCommand,
  type RuleImpact,
  type FieldView,
  type Condition,
  type PolicyCommand,
  type PolicyCreated,
} from "./api";

const operators: Record<string, string> = {
  equals: "is",
  in: "is any of",
  gte: "is at least",
  lt: "is less than",
};

export function RuleEditor({
  people,
  today,
  onSaved,
}: {
  people: Person[];
  today: string;
  onSaved: () => void;
}) {
  const [day, setDay] = useState(today);
  const [categoryId, setCategoryId] = useState("pay");
  const [categories, setCategories] = useState<Category[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [fields, setFields] = useState<FieldView[]>([]);
  const [command, setCommand] = useState<RuleCommand | null>(null);
  const [policy, setPolicy] = useState<PolicyCommand | null>(null);
  const [impact, setImpact] = useState<RuleImpact | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!day) return;
    let alive = true;
    setLoading(true);
    setLoadError("");
    Promise.all([
      get<Category[]>(`categories?as_of=${day}`),
      get<Rule[]>("rules"),
      get<FieldView[]>("rule-fields"),
    ])
      .then(([cats, list, registry]) => {
        if (alive) {
          setCategories(cats);
          setRules(list);
          setFields(registry);
        }
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
  }, [day, refresh]);
  const category = categories.find((c) => c.id === categoryId);
  const policyNames = Object.fromEntries(
    categories.flatMap((c) => c.policies).map((p) => [p.id, p.name]),
  );
  const current = rules
    .filter(
      (r) =>
        category?.policies.some((p) => p.id === r.policy_id) &&
        r.effective_from <= day &&
        (!r.effective_to || r.effective_to > day),
    )
    .sort(
      (a, b) =>
        a.priority - b.priority ||
        (a.rule_id < b.rule_id ? -1 : a.rule_id > b.rule_id ? 1 : 0),
    );
  const orderedIds =
    command?.action === "reorder"
      ? (command.ordered_rule_ids ?? [])
      : current.map((r) => r.rule_id);
  const displayed = orderedIds
    .map((id) => current.find((r) => r.rule_id === id))
    .filter((r): r is Rule => !!r);
  function reset() {
    setCommand(null);
    setPolicy(null);
    setImpact(null);
    setError("");
    setNotice("");
  }
  function base(action: RuleCommand["action"]): RuleCommand {
    return {
      request_id: crypto.randomUUID(),
      action,
      category_id: categoryId,
      effective_from: day,
      reason: "",
    };
  }
  function update(values: Partial<RuleCommand>) {
    setCommand(
      (c) => c && { ...c, ...values, request_id: crypto.randomUUID() },
    );
    setImpact(null);
    setError("");
    setNotice("");
  }
  function start(action: "create" | "edit" | "end", rule?: Rule) {
    reset();
    setCommand({
      ...base(action),
      ...(rule ? { rule_id: rule.rule_id } : {}),
      ...(action !== "end"
        ? {
            name: rule?.name ?? "",
            policy_id: rule?.policy_id ?? "",
            conditions: rule?.conditions ?? { all: [] },
          }
        : {}),
    });
  }
  function move(index: number, direction: number) {
    const ids = [...orderedIds];
    [ids[index], ids[index + direction]] = [ids[index + direction], ids[index]];
    setCommand({
      ...base("reorder"),
      reason: command?.action === "reorder" ? command.reason : "",
      ordered_rule_ids: ids,
    });
    setPolicy(null);
    setImpact(null);
    setError("");
    setNotice("");
  }
  async function submit(preview: boolean) {
    if (!command) return;
    setBusy(true);
    setError("");
    try {
      const payload = {
        ...command,
        ...(command.conditions
          ? {
              conditions: {
                all: command.conditions.all.map((c) => ({
                  ...c,
                  value: Array.isArray(c.value)
                    ? c.value.map((v) => v.trim()).filter(Boolean)
                    : typeof c.value === "string"
                      ? c.value.trim()
                      : c.value,
                })),
              },
            }
          : {}),
      };
      const result = await post<RuleImpact>(
        `rule-changes${preview ? "/preview" : ""}`,
        payload,
      );
      const changed =
        !preview &&
        JSON.stringify({
          changes: impact?.changes,
          manual: impact?.preserved_manual,
        }) !==
          JSON.stringify({
            changes: result.changes,
            manual: result.preserved_manual,
          });
      setImpact(result);
      if (result.saved) {
        setRefresh((n) => n + 1);
        onSaved();
        setNotice(
          `Saved. Assignments are up to date.${changed ? " Inputs changed since preview; the actual saved result is shown below." : ""}`,
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "The rule could not be saved.");
    } finally {
      setBusy(false);
    }
  }
  async function savePolicy() {
    if (!policy) return;
    setBusy(true);
    setError("");
    try {
      const result = await post<PolicyCreated>("policies", policy);
      setPolicy(null);
      setRefresh((n) => n + 1);
      onSaved();
      setNotice(
        `${result.name} was created. It is not assigned to anyone until you add a rule or manual exception.`,
      );
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The policy could not be created.",
      );
    } finally {
      setBusy(false);
    }
  }
  function conditionText(c: Condition) {
    const field = fields.find((f) => f.id === c.field);
    const label = (v: unknown) =>
      field?.choices.find((o) => o.id === v)?.name ??
      (typeof v === "boolean" ? (v ? "Yes" : "No") : String(v));
    return `${field?.label ?? c.field} ${operators[c.operator]} ${Array.isArray(c.value) ? c.value.map(label).join(", ") : label(c.value)}`;
  }
  function changeCondition(index: number, values: Partial<Condition>) {
    update({
      conditions: {
        all: (command?.conditions?.all ?? []).map((c, i) =>
          i === index ? { ...c, ...values } : c,
        ),
      },
    });
  }
  function newCondition(field: FieldView): Condition {
    return {
      field: field.id,
      operator: field.operators[0],
      value:
        field.kind === "boolean"
          ? true
          : field.kind === "tenure"
            ? 24
            : field.operators[0] === "in"
              ? []
              : "",
    };
  }
  const editing = !!command || !!policy;
  const unavailable = busy || loading || !!loadError || !day || day < today;
  return (
    <section className="panel rule-editor">
      <div className="panel-heading">
        <div>
          <h2>Assignment rules</h2>
          <p className="muted">
            Choose who receives each policy, then review the impact before
            saving.
          </p>
        </div>
      </div>
      <div className="rule-controls">
        <label>
          Category
          <select
            disabled={busy}
            value={categoryId}
            onChange={(e) => {
              reset();
              setCategoryId(e.target.value);
            }}
          >
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Effective date
          <input
            type="date"
            min={today}
            disabled={busy}
            value={day}
            onChange={(e) => {
              reset();
              setDay(e.target.value);
            }}
          />
        </label>
        <button
          disabled={unavailable || editing}
          onClick={() => start("create")}
        >
          Add rule
        </button>
        <button
          disabled={unavailable || editing}
          onClick={() => {
            reset();
            setPolicy({
              request_id: crypto.randomUUID(),
              category_id: categoryId,
              name: "",
              description: "",
              effective_from: day,
              reason: "",
            });
          }}
        >
          Create policy
        </button>
      </div>
      <p className="assignment-note">
        {category?.cardinality === "many"
          ? "All matching policies apply in this category. There is no need to order these rules."
          : "Rules are checked from top to bottom. The first match determines the policy. Put specific rules above company-wide defaults."}{" "}
        New rules start at the bottom.
      </p>
      {loading && (
        <p role="status" className="assignment-note">
          Loading rules…
        </p>
      )}
      {loadError && (
        <p role="alert" className="coverage-error">
          {loadError}{" "}
          <button onClick={() => setRefresh((n) => n + 1)}>Retry</button>
        </p>
      )}
      {!loading && !loadError && (
        <ol className="editable-rules">
          {displayed.map((r, index) => (
            <li key={r.rule_id}>
              <div>
                <strong>{r.name}</strong>
                <p>Assigns {policyNames[r.policy_id]}</p>
                <p className="muted">
                  From {dateLabel(r.effective_from)}
                  {r.effective_to
                    ? ` until ${dateLabel(r.effective_to)} (exclusive)`
                    : " onward"}
                </p>
                <small>
                  {r.conditions.all.length
                    ? r.conditions.all.map(conditionText).join("; and ")
                    : "Everyone in active employment"}
                </small>
              </div>
              <div className="rule-actions">
                {category?.cardinality !== "many" && (
                  <>
                    <button
                      aria-label={`Move ${r.name} up`}
                      disabled={
                        unavailable ||
                        index === 0 ||
                        (!!command && command.action !== "reorder") ||
                        !!policy ||
                        !!impact?.saved
                      }
                      onClick={() => move(index, -1)}
                    >
                      ↑ Move up
                    </button>
                    <button
                      aria-label={`Move ${r.name} down`}
                      disabled={
                        unavailable ||
                        index === displayed.length - 1 ||
                        (!!command && command.action !== "reorder") ||
                        !!policy ||
                        !!impact?.saved
                      }
                      onClick={() => move(index, 1)}
                    >
                      ↓ Move down
                    </button>
                  </>
                )}
                <button
                  disabled={unavailable || editing}
                  onClick={() => start("edit", r)}
                >
                  Edit
                </button>
                <button
                  disabled={unavailable || editing}
                  onClick={() => start("end", r)}
                >
                  End rule
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}
      {!loading && !current.length && (
        <p className="assignment-note">
          No rules in this category on the selected date.
        </p>
      )}
      {command && (
        <form
          className="override-form"
          onSubmit={(e) => {
            e.preventDefault();
            void submit(true);
          }}
        >
          <h3>
            {command.action === "create"
              ? "New assignment rule"
              : command.action === "edit"
                ? "Edit assignment rule"
                : command.action === "end"
                  ? "End this rule"
                  : "Review new rule order"}
          </h3>
          <p>
            Effective {dateLabel(day)}.{" "}
            {command.action === "end"
              ? "This rule will no longer apply from this date onward."
              : "Earlier rule versions and assignments stay in history."}
          </p>
          <fieldset disabled={unavailable || !!impact?.saved}>
            {command.conditions && (
              <>
                <label>
                  Rule name
                  <input
                    required
                    maxLength={200}
                    value={command.name ?? ""}
                    onChange={(e) => update({ name: e.target.value })}
                  />
                </label>
                <label>
                  Assign policy
                  <select
                    required
                    value={command.policy_id ?? ""}
                    onChange={(e) => update({ policy_id: e.target.value })}
                  >
                    <option value="">Choose policy</option>
                    {category?.policies.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="reason-field">
                  <h4>Employee matches all of these conditions</h4>
                  {!command.conditions.all.length && (
                    <p>No conditions means everyone in active employment.</p>
                  )}
                  {command.conditions.all.map((c, index) => {
                    const field = fields.find((f) => f.id === c.field)!;
                    const isLocation =
                      c.field === "country" || c.field === "state";
                    return (
                      <div className="condition-row" key={index}>
                        <label>
                          Employee information
                          <select
                            value={c.field}
                            onChange={(e) =>
                              changeCondition(
                                index,
                                newCondition(
                                  fields.find((f) => f.id === e.target.value)!,
                                ),
                              )
                            }
                          >
                            {fields.map((f) => (
                              <option key={f.id} value={f.id}>
                                {f.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Comparison
                          <select
                            value={c.operator}
                            onChange={(e) =>
                              changeCondition(index, {
                                operator: e.target.value,
                                value:
                                  e.target.value === "in"
                                    ? []
                                    : field.kind === "tenure"
                                      ? 24
                                      : field.kind === "boolean"
                                        ? true
                                        : "",
                              })
                            }
                          >
                            {field.operators.map((o) => (
                              <option key={o} value={o}>
                                {operators[o]}
                              </option>
                            ))}
                          </select>
                        </label>
                        {field.kind === "boolean" ? (
                          <label>
                            Value
                            <select
                              value={String(c.value)}
                              onChange={(e) =>
                                changeCondition(index, {
                                  value: e.target.value === "true",
                                })
                              }
                            >
                              <option value="true">Yes</option>
                              <option value="false">No</option>
                            </select>
                          </label>
                        ) : field.choices.length && c.operator === "in" ? (
                          <div
                            className="condition-choices"
                            role="group"
                            aria-label={`${field.label}: choose one or more`}
                          >
                            <span>Choose one or more</span>
                            {field.choices.map((o) => (
                              <label key={o.id}>
                                <input
                                  type="checkbox"
                                  checked={(c.value as string[]).includes(o.id)}
                                  onChange={(e) =>
                                    changeCondition(index, {
                                      value: e.target.checked
                                        ? [...(c.value as string[]), o.id]
                                        : (c.value as string[]).filter(
                                            (id) => id !== o.id,
                                          ),
                                    })
                                  }
                                />
                                {o.name}
                              </label>
                            ))}
                          </div>
                        ) : field.choices.length ? (
                          <label>
                            {c.operator === "in"
                              ? "Choose one or more"
                              : "Value"}
                            <select
                              required
                              multiple={c.operator === "in"}
                              value={
                                c.operator === "in"
                                  ? (c.value as string[])
                                  : String(c.value)
                              }
                              onChange={(e) =>
                                changeCondition(index, {
                                  value:
                                    c.operator === "in"
                                      ? Array.from(
                                          e.target.selectedOptions,
                                          (o) => o.value,
                                        )
                                      : e.target.value,
                                })
                              }
                            >
                              {c.operator !== "in" && (
                                <option value="">Choose value</option>
                              )}
                              {field.choices.map((o) => (
                                <option key={o.id} value={o.id}>
                                  {o.name}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : (
                          <label>
                            {field.kind === "tenure"
                              ? "Completed months"
                              : c.operator === "in"
                                ? "Values, separated by commas"
                                : isLocation
                                  ? "Location code"
                                  : "Value"}
                            <input
                              required
                              type={field.kind === "tenure" ? "number" : "text"}
                              min={field.kind === "tenure" ? 0 : undefined}
                              max={field.kind === "tenure" ? 1200 : undefined}
                              step={1}
                              placeholder={
                                field.kind === "tenure"
                                  ? "24"
                                  : isLocation
                                    ? "US"
                                    : "Enter value"
                              }
                              value={
                                Array.isArray(c.value)
                                  ? c.value.join(",")
                                  : String(c.value)
                              }
                              onChange={(e) =>
                                changeCondition(index, {
                                  value:
                                    field.kind === "tenure"
                                      ? e.target.value === ""
                                        ? ""
                                        : Number(e.target.value)
                                      : c.operator === "in"
                                        ? (isLocation
                                            ? e.target.value.toUpperCase()
                                            : e.target.value
                                          ).split(",")
                                        : isLocation
                                          ? e.target.value.toUpperCase()
                                          : e.target.value,
                                })
                              }
                            />
                          </label>
                        )}
                        <button
                          type="button"
                          onClick={() =>
                            update({
                              conditions: {
                                all: command.conditions!.all.filter(
                                  (_, i) => i !== index,
                                ),
                              },
                            })
                          }
                        >
                          Remove condition
                        </button>
                      </div>
                    );
                  })}
                  <button
                    type="button"
                    onClick={() =>
                      update({
                        conditions: {
                          all: [
                            ...command.conditions!.all,
                            newCondition(fields[0]),
                          ],
                        },
                      })
                    }
                  >
                    Add condition
                  </button>
                </div>
              </>
            )}
            <label className="reason-field">
              Reason
              <textarea
                required
                maxLength={1000}
                value={command.reason}
                onChange={(e) => update({ reason: e.target.value })}
              />
            </label>
          </fieldset>
          <div className="override-actions">
            {!impact?.saved && (
              <button className="primary" type="submit" disabled={unavailable}>
                {busy ? "Working…" : "Preview assignment changes"}
              </button>
            )}
            {impact && !impact.saved && !impact.gaps.length && (
              <button
                className="primary"
                type="button"
                disabled={unavailable}
                onClick={() => void submit(false)}
              >
                Save rule change
              </button>
            )}
            <button type="button" disabled={busy} onClick={reset}>
              {impact?.saved ? "Done" : "Cancel"}
            </button>
          </div>
        </form>
      )}
      {policy && (
        <form
          className="override-form"
          onSubmit={(e) => {
            e.preventDefault();
            void savePolicy();
          }}
        >
          <h3>Create a policy in {category?.name}</h3>
          <p>
            Available from {dateLabel(day)}. Creating a policy does not assign
            it to anyone.
          </p>
          <fieldset disabled={unavailable}>
            <label>
              Policy name
              <input
                required
                maxLength={200}
                value={policy.name}
                onChange={(e) => setPolicy({ ...policy, name: e.target.value })}
              />
            </label>
            <label>
              Description
              <textarea
                required
                maxLength={2000}
                value={policy.description}
                onChange={(e) =>
                  setPolicy({ ...policy, description: e.target.value })
                }
              />
            </label>
            <label className="reason-field">
              Reason
              <textarea
                required
                maxLength={1000}
                value={policy.reason}
                onChange={(e) =>
                  setPolicy({ ...policy, reason: e.target.value })
                }
              />
            </label>
          </fieldset>
          <div className="override-actions">
            <button className="primary" disabled={unavailable}>
              Create policy
            </button>
            <button type="button" disabled={busy} onClick={reset}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="coverage-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="assignment-note">
          {notice}
        </p>
      )}
      {impact && (
        <div className="rule-impact">
          <h3>
            {impact.saved ? "Saved assignment changes" : "Assignment impact"}
          </h3>
          <p>
            {new Set(impact.changes.map((c) => c.employee_id)).size} employees
            have policy changes. Future transitions are included.
          </p>
          {impact.gaps.length > 0 && (
            <div role="alert" className="coverage-error">
              <strong>This change cannot be saved yet.</strong>
              <p>
                Keep a fallback rule or add manual assignments for these
                employees:
              </p>
              <ul>
                {impact.gaps.map((g, i) => (
                  <li key={i}>
                    {people.find((p) => p.id === g.employee_id)?.name}:{" "}
                    {g.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {impact.changes.length > 0 ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>From / until</th>
                    <th>Gains</th>
                    <th>Loses</th>
                  </tr>
                </thead>
                <tbody>
                  {impact.changes.map((c, i) => (
                    <tr key={i}>
                      <td>
                        {people.find((p) => p.id === c.employee_id)?.name}
                      </td>
                      <td>
                        {dateLabel(c.effective_from)} →{" "}
                        {c.effective_to
                          ? `${dateLabel(c.effective_to)} (exclusive)`
                          : "ongoing"}
                      </td>
                      <td>{c.gained.join(", ") || "—"}</td>
                      <td>{c.lost.join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>
              No policies change. The rule and its explanation evidence may
              still change.
            </p>
          )}
          {impact.preserved_manual.length > 0 && (
            <details>
              <summary>
                {impact.preserved_manual.length} manual exceptions remain
                unchanged
              </summary>
              <ul>
                {impact.preserved_manual.map((m, i) => (
                  <li key={i}>
                    {people.find((p) => p.id === m.employee_id)?.name} —{" "}
                    {m.action === "exclude"
                      ? "Excluded: "
                      : m.action === "clear"
                        ? "Left unassigned: "
                        : ""}
                    {m.policy_name}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
