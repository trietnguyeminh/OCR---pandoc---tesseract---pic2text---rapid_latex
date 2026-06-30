import { downloadDocxUrl, reportJsonUrl } from "../api";
import type { JobInfo } from "../api";

function Stat({ label, value, accent }: { label: string; value: number | string; accent?: boolean }) {
  return (
    <div className={[
      "rounded-xl border p-3 text-center",
      accent ? "border-brand-indigo/40 bg-indigo-50" : "border-slate-200 bg-white",
    ].join(" ")}>
      <div className="text-2xl font-bold text-slate-800 tabular-nums">{value}</div>
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
    </div>
  );
}

export function Result({ job }: { job: JobInfo }) {
  const r = job.report!;
  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-3">
        <a
          href={downloadDocxUrl(job.job_id)}
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-blue to-brand-purple px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/20 transition hover:brightness-110"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path d="M12 3v12m0 0l-4-4m4 4l4-4M5 21h14" stroke="currentColor"
                  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Download .docx
        </a>
        <a
          href={reportJsonUrl(job.job_id)}
          target="_blank"
          className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-brand-blue"
        >
          Download report JSON
        </a>
      </div>

      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4">
        <Stat label="Pages" value={r.pages} />
        <Stat label="Text blocks" value={r.detected_text_blocks} />
        <Stat label="Tables" value={r.detected_tables} />
        <Stat label="Figures" value={r.detected_figures} />
        <Stat label="Formulas" value={r.detected_formulas} />
        <Stat label="Editable eq." value={r.editable_equations} accent />
        <Stat label="Image eq." value={r.image_fallback_equations} />
        <Stat label="HF removed" value={r.removed_headers_footers} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Summary / preview
          </div>
          <pre className="log-scroll h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
{job.preview ?? ""}
          </pre>
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Engines &amp; warnings
          </div>
          <div className="h-48 space-y-2 overflow-auto rounded-lg border border-slate-200 bg-white p-3 text-xs">
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(r.engines_used).map(([k, v]) => (
                <span key={k} className="rounded-full bg-indigo-50 px-2 py-0.5 font-medium text-brand-indigo">
                  {k}: {v}
                </span>
              ))}
            </div>
            <span className={[
              "inline-block rounded-full px-2 py-0.5 font-medium",
              r.classification === "born_digital"
                ? "bg-emerald-50 text-emerald-700"
                : "bg-amber-50 text-amber-700",
            ].join(" ")}>
              {r.classification}
            </span>
            {r.warnings.length === 0 ? (
              <div className="text-emerald-600">No warnings 🎉</div>
            ) : (
              <ul className="list-disc space-y-1 pl-4 text-amber-700">
                {r.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
