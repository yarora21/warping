import type { components } from "./api.generated";

export type Person = components["schemas"]["Person"];
export type Category = components["schemas"]["Category"];
export type Settings = components["schemas"]["Settings"];

export async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api/${path}`);
  if (!response.ok)
    throw new Error("We couldn’t load your company data. Please try again.");
  return response.json() as Promise<T>;
}

export type Interval = components["schemas"]["Interval"];
export type Rule = components["schemas"]["RuleView"];
export type Report = components["schemas"]["AssignmentReport"];

export async function queryAssignments(
  query: components["schemas"]["AssignmentQuery"],
): Promise<Report> {
  const response = await fetch("/api/assignments/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(query),
  });
  if (!response.ok)
    throw new Error(
      "Assignments could not be loaded. Check the date and try again.",
    );
  return response.json();
}

export const loadDirectory = () =>
  Promise.all([
    get<Settings>("settings"),
    get<Person[]>("people"),
    get<Category[]>("categories"),
  ]);

// Date-only values stay strings. No timezone conversion for effective dates.
export function dateLabel(value: string): string {
  const [year, month, day] = value.split("-");
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  return `${months[Number(month) - 1]} ${Number(day)}, ${year}`;
}
