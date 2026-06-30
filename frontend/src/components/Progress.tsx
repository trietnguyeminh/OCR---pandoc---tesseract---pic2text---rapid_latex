import type { JobInfo } from "../api";

export function Progress({ job }: { job: JobInfo }) {
  const pct = Math.min(100, Math.max(0, job.progress));
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="font-semibold text-slate-700 capitalize">
          {job.status === "running" ? `Working · ${job.stage}` : job.status}
        </span>
        <span className="tabular-nums text-slate-500">{pct}%</span>
      </div>
      <div className="relative h-3 w-full overflow-hidden rounded-full bg-slate-200">
        <div
          className="shimmer relative h-full rounded-full bg-gradient-to-r from-brand-blue to-brand-purple transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="mt-4">
        <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Conversion log
        </div>
        <div className="log-scroll h-44 overflow-y-auto rounded-lg bg-slate-900 p-3 font-mono text-xs leading-relaxed text-slate-200">
          {job.log.length === 0 && <div className="text-slate-500">waiting…</div>}
          {job.log.map((l, i) => (
            <div key={i} className="whitespace-pre-wrap">
              {l}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
