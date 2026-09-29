import type { Metadata } from "next";
import Link from "next/link";

import { Section } from "@/components/Section";
import { StatusBadge } from "@/components/StatusBadge";
import { Table } from "@/components/Table";
import { getMeta, getSources } from "@/lib/data";
import { date, listing, period, vintage } from "@/lib/format";
import { REPO_URL } from "@/lib/site";
import type { Source, Status } from "@/lib/types";

export const metadata: Metadata = {
  title: "data",
  description:
    "Where every number on the site comes from: the endpoints, how often they update, the " +
    "latest observation, licences and CSV downloads.",
};

function latest(values: (string | null)[]): string | null {
  const known = values.filter((v): v is string => v !== null).sort();
  return known.at(-1) ?? null;
}

export default function DataPage() {
  const meta = getMeta();
  const sources = getSources();
  const fetched = new Map(meta.sources.map((s) => [s.id, s]));

  /** A fetched source's state from meta.json; a static or derived one's from its series. */
  function status(s: Source): Status {
    const m = fetched.get(s.id);
    if (m) return m.status;
    return s.series.some((x) => x.status === "stale") ? "stale" : "ok";
  }
  /** The freshness column: the latest observation, but for the WEO, whose forecasts run
   * years ahead, the vintage. */
  function latestCell(s: Source): string {
    if (s.id === "imf_datamapper" && meta.through.weo_vintage) {
      return `${vintage(meta.through.weo_vintage)} vintage`;
    }
    const last = fetched.get(s.id)?.last_obs ?? latest(s.series.map((x) => x.last));
    return last === null ? "—" : period(last);
  }
  const downloads = sources.reduce((n, s) => n + s.series.filter((x) => x.csv).length, 0);
  const closed = sources.filter((s) => !s.redistribute);

  return (
    <article>
      <header className="pt-10 sm:pt-16">
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">data</h1>
        <p className="mt-5 max-w-3xl text-lg leading-snug sm:text-xl">
          Where every number comes from, how fresh it is, and what you can download.
        </p>
        <p className="mt-4 max-w-2xl text-sm text-muted">
          {meta.sources.length} public sources are fetched on a schedule; the rest are frozen
          seeds and the series this site builds from the others. {downloads} series can be
          downloaded as CSV (<span className="num">date,value</span>).{" "}
          {listing(closed.map((s) => s.publisher))} data are used but not offered for download,
          because their terms do not clearly allow it.
        </p>
      </header>

      <Section id="sources" title="sources">
        <Table
          caption="The sources: publisher, endpoint, update frequency, latest observation, status and licence."
          minWidth="56rem"
          columns={[
            { label: "publisher", align: "left" },
            { label: "endpoint", align: "left" },
            { label: "frequency", align: "left" },
            { label: "latest", align: "left" },
            { label: "status", align: "left" },
            { label: "licence", align: "left" },
          ]}
          rows={sources.map((s) => ({
            key: s.id,
            cells: [
              <span key="p" className="block min-w-40">
                <a href={`#${s.id}`}>{s.publisher}</a>
                <span className="block text-xs text-muted">{s.name}</span>
              </span>,
              <span key="e" className="block w-60 text-xs break-all">
                {s.method && <span className="text-muted">{s.method} </span>}
                <code>{s.url}</code>
              </span>,
              s.frequency,
              <span key="l" className="num">
                {latestCell(s)}
              </span>,
              <StatusBadge key="s" status={status(s)} />,
              <span key="c" className="block min-w-48 text-xs">
                {s.license}
              </span>,
            ],
          }))}
        />
        {meta.stale.length > 0 && (
          <p className="mt-3 text-sm">
            Stale on the latest run: {meta.stale.join(", ")}. Their previous data are shown.
          </p>
        )}
      </Section>

      <Section
        id="series"
        title="series and downloads"
        intro={
          <p>
            Every series the site reads, by source. The derived series are this project&rsquo;s
            own constructions from the ones above; the <Link href="/method">method</Link> says
            how each is made. Please cite the original publisher as well as this site.
          </p>
        }
      >
        <div className="space-y-12">
          {sources.map((s) => (
            <div key={s.id} id={s.id} className="scroll-mt-6">
              <h3 className="font-medium">
                {s.publisher} <span className="font-normal text-muted">· {s.name}</span>
              </h3>
              <p className="mt-1 text-xs text-muted">
                {s.redistribute
                  ? "CSV downloads below."
                  : "Used on the site; not offered for download."}{" "}
                Licence: {s.license}.
              </p>
              <div className="mt-3">
                <Table
                  caption={`Series from ${s.publisher}: label, id, units, first and last observation, status and CSV download.`}
                  minWidth="50rem"
                  columns={[
                    { label: "series", align: "left" },
                    { label: "units", align: "left" },
                    { label: "first" },
                    { label: "last" },
                    { label: "status", align: "left" },
                    { label: "csv", align: "left" },
                  ]}
                  rows={s.series.map((x) => ({
                    key: x.id,
                    cells: [
                      <span key="l" className="block min-w-56">
                        {x.label}
                        <span className="block text-xs text-muted">
                          <code>{x.id}</code>
                        </span>
                      </span>,
                      <span key="u" className="block min-w-32 text-xs">
                        {x.units}
                      </span>,
                      x.first === null ? "—" : period(x.first),
                      x.last === null ? "—" : period(x.last),
                      <StatusBadge key="s" status={x.status} />,
                      x.csv === null ? (
                        <span key="c" className="text-muted">
                          —
                        </span>
                      ) : (
                        <a key="c" href={`/${x.csv}`}>
                          csv
                        </a>
                      ),
                    ],
                  }))}
                />
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section id="schedule" title="update schedule">
        <div className="max-w-3xl space-y-3 text-sm">
          <p>
            A scheduled GitHub Action fetches the data at 02:41 UTC on the 3rd, 12th and 20th of
            each month: the World Bank&rsquo;s Pink Sheet is usually out by the 2nd, the NSO
            publishes trade and consumer prices by about the 9th to the 11th, and the 20th
            catches anything late. It then rebuilds every number and sentence on the site and
            publishes them if anything changed. The latest build is from{" "}
            <span className="num">{date(meta.generated_at)}</span>.
          </p>
          <p>
            Each source is fetched on its own and checked: no gaps, values within sensible
            bounds, no older latest date than before, and no revisions beyond a set tolerance
            (the IMF&rsquo;s and World Bank&rsquo;s annual data are expected to revise, and those
            revisions are counted). A source that fails keeps its previous data and is marked{" "}
            <StatusBadge status="stale" />. Where a second source exists, it fills the months
            after the primary one ends, and the series is marked{" "}
            <StatusBadge status="fallback" />. If three or more sources fail, nothing is
            published and the run fails.
          </p>
          <p>
            Revisions accepted on the latest run:{" "}
            {Object.entries(meta.revisions)
              .map(([k, n]) => `${k} ${n}`)
              .join(", ")}
            . Code and history: <a href={REPO_URL}>{REPO_URL.replace("https://", "")}</a>.
          </p>
        </div>
      </Section>
    </article>
  );
}
