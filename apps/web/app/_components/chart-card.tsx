interface Props {
  label: string;
  hint?: string;
  children: React.ReactNode;
}

export function ChartCard({ label, hint, children }: Props) {
  return (
    <section className="rounded-lg border border-border bg-card/30 p-4">
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </h3>
        {hint && <p className="text-[11px] text-muted-foreground/80">{hint}</p>}
      </header>
      {children}
    </section>
  );
}
