import type { components } from "./api.generated";

export type Person = components["schemas"]["Person"];
export type Category = components["schemas"]["Category"];
export type Settings = components["schemas"]["Settings"];

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api/${path}`);
  if (!response.ok)
    throw new Error("We couldn’t load your company data. Please try again.");
  return response.json() as Promise<T>;
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
