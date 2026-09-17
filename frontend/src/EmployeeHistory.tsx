import { useEffect, useState } from "react";
import { dateLabel, get, type EmployeeEvent } from "./api";

export function EmployeeHistory({
  employeeId,
  today,
  onSelectDate,
}: {
  employeeId: string;
  today: string;
  onSelectDate: (date: string) => void;
}) {
  const [events, setEvents] = useState<EmployeeEvent[] | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    setEvents(null);
    setError("");
    get<EmployeeEvent[]>(`people/${employeeId}/history`)
      .then((rows) => {
        if (alive) setEvents(rows);
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [employeeId, retry]);
  return (
    <section className="panel employee-history">
      <div className="panel-heading">
        <div>
          <h2>Employee history</h2>
          <p className="muted">
            Hires, moves, and team changes that help explain assignment changes.
          </p>
        </div>
      </div>
      <p className="assignment-note">
        Effective dates, newest first. Policy rules, tenure milestones, and
        manual exceptions can also change assignments.
      </p>
      {error && (
        <p className="coverage-error" role="alert">
          {error} <button onClick={() => setRetry((n) => n + 1)}>Retry</button>
        </p>
      )}
      {!events && !error && (
        <p className="assignment-note" role="status">
          Loading employee history…
        </p>
      )}
      {events?.length === 0 && (
        <p className="assignment-note">No recorded employee changes.</p>
      )}
      <ol className="employee-events">
        {events?.map((event) => (
          <li key={event.id}>
            <div className="employee-event-heading">
              <div>
                <strong>{event.title}</strong>
                <p>
                  {dateLabel(event.effective_date)}
                  {event.effective_date > today && (
                    <span className="pill">Scheduled</span>
                  )}
                </p>
              </div>
              <a
                className="text-link"
                href="#policy-assignments"
                onClick={() => onSelectDate(event.effective_date)}
              >
                View assignments on this date →
              </a>
            </div>
            <dl className="employee-event-changes">
              {event.changes.map((change) => (
                <div key={change.field}>
                  <dt>{change.field}</dt>
                  <dd>
                    {change.before === null ? (
                      change.after
                    ) : (
                      <>
                        {change.before} →{" "}
                        <strong>{change.after ?? "Employment ended"}</strong>
                      </>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
            {event.reasons.map((reason, i) => (
              <p className="employee-event-reason" key={i}>
                {reason.reason} <span className="muted">— {reason.actor}</span>
              </p>
            ))}
          </li>
        ))}
      </ol>
    </section>
  );
}
