import type { Status } from "@/lib/types";

const TITLES: Record<Status, string> = {
  ok: "updated on the latest run",
  stale: "the latest run could not update this source; the previous data are shown",
  fallback: "the primary source is stale; a second source fills the latest months",
};

/** A source's state: quiet when it is ok, boxed when it is stale or on a fallback. */
export function StatusBadge({ status }: { status: Status }) {
  if (status === "ok") {
    return (
      <span className="text-xs text-muted" title={TITLES.ok}>
        ok
      </span>
    );
  }
  return (
    <span
      className={`border px-1.5 py-0.5 text-xs text-fg ${status === "stale" ? "border-fg" : "border-line"}`}
      title={TITLES[status]}
    >
      {status}
    </span>
  );
}
