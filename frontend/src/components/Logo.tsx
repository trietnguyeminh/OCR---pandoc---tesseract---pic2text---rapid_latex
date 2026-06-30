export function LogoMark({ size = 44 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none"
         xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <defs>
        <linearGradient id="fdg" x1="0" y1="0" x2="64" y2="64"
                        gradientUnits="userSpaceOnUse">
          <stop stopColor="#2563eb" />
          <stop offset="1" stopColor="#7c3aed" />
        </linearGradient>
      </defs>
      <rect x="6" y="6" width="52" height="52" rx="13" fill="url(#fdg)" />
      <rect x="16" y="15" width="20" height="26" rx="3" fill="#fff" opacity="0.35" />
      <rect x="22" y="20" width="22" height="28" rx="3" fill="#fff" />
      <path d="M38 20 v6 h6" fill="none" stroke="#c7d2fe" strokeWidth="2"
            strokeLinejoin="round" />
      <text x="33" y="42" fontFamily="Cambria, Georgia, serif" fontSize="20"
            fontStyle="italic" fill="url(#fdg)" textAnchor="middle">
        {"∫"}
      </text>
      <path d="M11 50 h9 m0 0 l-3 -3 m3 3 l-3 3" stroke="#fff" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  );
}

export function Logo() {
  return (
    <div className="flex items-center gap-3">
      <LogoMark />
      <div className="leading-tight">
        <div className="text-xl font-extrabold tracking-tight text-slate-800">
          FormuDoc <span className="text-brand-indigo">Converter</span>
        </div>
        <div className="text-xs font-medium text-slate-500">
          PDF → Word with layout, tables &amp; editable math
        </div>
      </div>
    </div>
  );
}
