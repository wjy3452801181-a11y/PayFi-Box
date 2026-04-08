type RoleCardProps = {
  title: string;
  subtitle: string;
  description: string;
  bullets: string[];
};

export function RoleCard({
  title,
  subtitle,
  description,
  bullets,
}: RoleCardProps) {
  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-6 shadow-panel">
      <div className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-700">
          {subtitle}
        </p>
        <h3 className="mt-2 text-2xl font-semibold text-slate-900">{title}</h3>
      </div>
      <p className="text-sm leading-6 text-slate-600">{description}</p>
      <ul className="mt-5 space-y-2 text-sm text-slate-700">
        {bullets.map((bullet) => (
          <li key={bullet} className="flex gap-2">
            <span className="mt-1 h-2 w-2 rounded-full bg-teal-600" />
            <span>{bullet}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}

