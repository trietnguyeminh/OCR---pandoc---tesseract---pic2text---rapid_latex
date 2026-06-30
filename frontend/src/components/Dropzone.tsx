import { useCallback, useRef, useState } from "react";

interface Props {
  onFile: (file: File) => void;
  disabled?: boolean;
}

export function Dropzone({ onFile, disabled }: Props) {
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const pick = useCallback(
    (files: FileList | null) => {
      if (!files || !files.length) return;
      const f = files[0];
      if (!f.name.toLowerCase().endsWith(".pdf")) {
        alert("Please choose a .pdf file");
        return;
      }
      onFile(f);
    },
    [onFile]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        if (!disabled) pick(e.dataTransfer.files);
      }}
      onClick={() => !disabled && input.current?.click()}
      className={[
        "cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition",
        drag
          ? "border-brand-indigo bg-indigo-50/70"
          : "border-slate-300 bg-white/70 hover:border-brand-blue hover:bg-indigo-50/40",
        disabled ? "pointer-events-none opacity-60" : "",
      ].join(" ")}
    >
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(e) => pick(e.target.files)}
      />
      <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-brand-blue to-brand-purple text-white">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
          <path d="M12 16V4m0 0L7 9m5-5l5 5M5 20h14" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <p className="text-base font-semibold text-slate-700">
        Drag &amp; drop a PDF here
      </p>
      <p className="mt-1 text-sm text-slate-500">
        or <span className="font-medium text-brand-indigo">browse</span> — max 100&nbsp;MB
      </p>
    </div>
  );
}
