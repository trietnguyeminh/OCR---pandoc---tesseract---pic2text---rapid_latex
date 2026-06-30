import type { ConvertMode, ConvertOptions } from "../api";

const MODES: { id: ConvertMode; title: string; desc: string }[] = [
  { id: "fast", title: "Fast Convert", desc: "Text layer only — quickest" },
  { id: "scientific", title: "Scientific Accurate", desc: "Layout + tables + formulas" },
  { id: "ocr_heavy", title: "OCR Heavy", desc: "Force OCR on every page" },
];

const TOGGLES: { key: keyof ConvertOptions; label: string }[] = [
  { key: "preserve_layout", label: "Preserve layout" },
  { key: "detect_formulas", label: "Detect formulas" },
  { key: "convert_formulas_editable", label: "Convert formulas to editable Word equations" },
  { key: "detect_tables", label: "Detect tables" },
  { key: "remove_headers_footers", label: "Remove repeated headers / footers" },
];

interface Props {
  options: ConvertOptions;
  setOptions: (o: ConvertOptions) => void;
  disabled?: boolean;
}

export function OptionsPanel({ options, setOptions, disabled }: Props) {
  return (
    <div className={disabled ? "opacity-60 pointer-events-none" : ""}>
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Conversion mode
      </h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {MODES.map((m) => {
          const active = options.mode === m.id;
          return (
            <button
              key={m.id}
              onClick={() => setOptions({ ...options, mode: m.id })}
              className={[
                "rounded-xl border p-3 text-left transition",
                active
                  ? "border-brand-indigo bg-indigo-50 ring-2 ring-brand-indigo/30"
                  : "border-slate-200 bg-white hover:border-brand-blue",
              ].join(" ")}
            >
              <div className="text-sm font-semibold text-slate-800">{m.title}</div>
              <div className="text-xs text-slate-500">{m.desc}</div>
            </button>
          );
        })}
      </div>

      <h3 className="mb-2 mt-5 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Options
      </h3>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {TOGGLES.map((t) => (
          <label
            key={t.key}
            className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 hover:border-brand-blue"
          >
            <input
              type="checkbox"
              className="h-4 w-4 accent-brand-indigo"
              checked={options[t.key] as boolean}
              onChange={(e) => setOptions({ ...options, [t.key]: e.target.checked })}
            />
            {t.label}
          </label>
        ))}
      </div>
    </div>
  );
}
