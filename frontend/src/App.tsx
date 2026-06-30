import { useEffect, useRef, useState } from "react";
import {
  analyzePdf, checkHealth, getJob, startConvert,
} from "./api";
import type { AnalyzeResponse, ConvertOptions, JobInfo } from "./api";
import { Logo } from "./components/Logo";
import { Dropzone } from "./components/Dropzone";
import { OptionsPanel } from "./components/OptionsPanel";
import { Progress } from "./components/Progress";
import { Result } from "./components/Result";

const DEFAULT_OPTIONS: ConvertOptions = {
  mode: "scientific",
  preserve_layout: true,
  detect_formulas: true,
  convert_formulas_editable: true,
  detect_tables: true,
  remove_headers_footers: true,
};

function prettySize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

const CAP_LABELS: Record<string, string> = {
  gemini: "Gemini (best, API)",
  pandoc: "Editable equations (pandoc)",
  tesseract: "OCR (tesseract)",
  pix2text: "Pix2Text full-page",
  rapid_latex: "RapidLaTeXOCR (offline)",
};

export default function App() {
  const [caps, setCaps] = useState<Record<string, boolean> | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [options, setOptions] = useState<ConvertOptions>(DEFAULT_OPTIONS);
  const [job, setJob] = useState<JobInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiKeys, setApiKeys] = useState<string[]>([]);
  const [keyInput, setKeyInput] = useState("");
  const poll = useRef<number | null>(null);

  useEffect(() => {
    checkHealth().then(setCaps);
    return () => { if (poll.current) window.clearInterval(poll.current); };
  }, []);

  async function handleFile(f: File) {
    reset();
    setFile(f);
    setAnalyzing(true);
    try {
      setAnalysis(await analyzePdf(f));
    } catch (e: any) {
      setError(e.message ?? "Failed to analyze PDF");
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleConvert() {
    if (!analysis) return;
    setError(null);
    try {
      const { job_id } = await startConvert(analysis.file_id, options, analysis.filename, apiKeys);
      poll.current = window.setInterval(async () => {
        try {
          const info = await getJob(job_id);
          setJob(info);
          if (info.status === "done" || info.status === "error") {
            if (poll.current) window.clearInterval(poll.current);
          }
        } catch (e: any) {
          setError(e.message);
          if (poll.current) window.clearInterval(poll.current);
        }
      }, 700);
    } catch (e: any) {
      setError(e.message ?? "Failed to start conversion");
    }
  }

  function addKey() {
    const k = keyInput.trim();
    if (k) {
      setApiKeys((prev) => [...prev, k]);
      setKeyInput("");
    }
  }
  const maskKey = (k: string) =>
    k.length <= 12 ? k : `${k.slice(0, 6)}…${k.slice(-3)}`;

  function reset() {
    if (poll.current) window.clearInterval(poll.current);
    setFile(null); setAnalysis(null); setJob(null); setError(null);
    setOptions(DEFAULT_OPTIONS); setApiKeys([]); setKeyInput("");
  }

  const converting = !!job && (job.status === "queued" || job.status === "running");
  const done = job?.status === "done";

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <header className="mb-6 flex items-center justify-between">
        <Logo />
        {caps && (
          <div className="hidden flex-wrap justify-end gap-1.5 sm:flex">
            {Object.keys(CAP_LABELS).map((k) => (
              <span
                key={k}
                title={CAP_LABELS[k]}
                className={[
                  "rounded-full px-2 py-0.5 text-[11px] font-medium",
                  caps[k] ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-400",
                ].join(" ")}
              >
                {caps[k] ? "● " : "○ "}{k}
              </span>
            ))}
          </div>
        )}
      </header>

      {caps === null && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Backend not reachable on <code>/health</code>. Start it with{" "}
          <code>uvicorn app.main:app --port 8000</code>.
        </div>
      )}

      <main className="rounded-3xl border border-white/60 bg-white/70 p-6 shadow-xl shadow-indigo-500/5 backdrop-blur">
        {/* Step 1: upload */}
        {!analysis && (
          <Dropzone onFile={handleFile} disabled={analyzing} />
        )}
        {analyzing && (
          <p className="mt-4 text-center text-sm text-slate-500">Analyzing PDF…</p>
        )}

        {/* Step 2: file info + options */}
        {analysis && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-red-50 text-red-500">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                    <path d="M7 3h7l5 5v13a0 0 0 01 0 0H7z" stroke="currentColor"
                          strokeWidth="1.6" />
                    <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.6" />
                  </svg>
                </div>
                <div>
                  <div className="font-semibold text-slate-800">{analysis.filename}</div>
                  <div className="text-xs text-slate-500">
                    {prettySize(analysis.size_bytes)} · {analysis.pages} page
                    {analysis.pages !== 1 ? "s" : ""} ·{" "}
                    <span className={analysis.classification === "born_digital"
                      ? "text-emerald-600" : "text-amber-600"}>
                      {analysis.classification}
                    </span>
                    {analysis.scanned_pages > 0 && ` · ${analysis.scanned_pages} scanned`}
                  </div>
                </div>
              </div>
              {!converting && (
                <button onClick={reset}
                        className="text-sm font-medium text-slate-500 hover:text-slate-700">
                  Choose another
                </button>
              )}
            </div>

            {!done && (
              <OptionsPanel options={options} setOptions={setOptions} disabled={converting} />
            )}

            {!job && (
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  AI Council keys <span className="font-normal lowercase">(tuỳ chọn — nhiều model phản biện chéo)</span>
                </div>
                <p className="mb-2 text-xs text-slate-500">
                  Nhập 1 key rồi Enter; lặp lại để thêm. Bỏ trống = không dùng (chạy luồng thường).
                  Mặc định là Gemini; muốn hãng khác ghi <code>provider:key</code> (openrouter:, openai:, anthropic:).
                </p>
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={keyInput}
                    onChange={(e) => setKeyInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addKey(); } }}
                    placeholder="dán API key rồi nhấn Enter…"
                    className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-indigo focus:outline-none"
                  />
                  <button onClick={addKey} type="button"
                    className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700">
                    Thêm
                  </button>
                </div>
                {apiKeys.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {apiKeys.map((k, i) => (
                      <span key={i} className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-brand-indigo">
                        seat {i + 1}: {maskKey(k)}
                        <button type="button" onClick={() => setApiKeys(apiKeys.filter((_, j) => j !== i))}
                          className="ml-0.5 text-brand-indigo/60 hover:text-brand-indigo">×</button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {!job && (
              <button
                onClick={handleConvert}
                className="w-full rounded-xl bg-gradient-to-r from-brand-blue to-brand-purple py-3 text-base font-bold text-white shadow-lg shadow-indigo-500/25 transition hover:brightness-110 active:scale-[.99]"
              >
                Convert to Word ✦
              </button>
            )}

            {job && !done && <Progress job={job} />}
            {done && (
              <>
                <Progress job={job!} />
                <div className="mt-6 border-t border-slate-200 pt-6">
                  <Result job={job!} />
                </div>
                <button onClick={reset}
                        className="mt-5 w-full rounded-xl border border-slate-300 bg-white py-2.5 text-sm font-semibold text-slate-700 hover:border-brand-blue">
                  Convert another PDF
                </button>
              </>
            )}
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
      </main>

      <footer className="mt-6 text-center text-xs text-slate-400">
        FormuDoc Converter · 3-tier pipeline (classify → layout → formula) ·
        ideas from Nougat, DocLayNet, PubLayNet, TrOCR, PubTables-1M, Docling &amp; Marker
      </footer>
    </div>
  );
}
