import Link from "next/link";

/** The top of an analysis page: its title, the generated takeaway and how to read it. */
export function PageHeader({
  title,
  takeaway,
  children,
}: {
  title: string;
  takeaway: string;
  children: React.ReactNode;
}) {
  return (
    <header className="pt-10 sm:pt-16">
      <p className="text-sm text-muted">
        <Link href="/">tugrik</Link> ·
      </p>
      <h1 className="mt-1 text-3xl font-medium tracking-tight sm:text-4xl">{title}</h1>
      <p className="mt-6 max-w-3xl text-xl leading-snug sm:text-2xl">{takeaway}</p>
      <div className="mt-8 max-w-3xl">
        <h2 className="text-sm text-muted">how to read this</h2>
        <div className="mt-2 space-y-3">{children}</div>
      </div>
    </header>
  );
}

export function Section({
  id,
  title,
  intro,
  children,
}: {
  id: string;
  title: string;
  intro?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="mt-16">
      <h2 id={id} className="scroll-mt-6 text-lg font-medium">
        {title}
      </h2>
      {intro && <div className="mt-1 max-w-2xl space-y-2 text-sm text-muted">{intro}</div>}
      <div className={intro ? "mt-6" : "mt-3"}>{children}</div>
    </section>
  );
}

/** A chart's generated takeaway sentence, above the chart it describes. */
export function Takeaway({ children }: { children: React.ReactNode }) {
  return <p className="mb-6 max-w-3xl text-base leading-snug sm:text-lg">{children}</p>;
}

/** The caveats at the foot of a page. */
export function Caveats({ children }: { children: React.ReactNode }) {
  return (
    <Section id="caveats" title="caveats">
      <ul className="max-w-3xl list-disc space-y-2 pl-5 text-sm text-muted marker:text-line">
        {children}
      </ul>
      <p className="mt-6 text-sm">
        <Link href="/method">How the numbers are made</Link> ·{" "}
        <Link href="/data">the data and downloads</Link>
      </p>
    </Section>
  );
}
