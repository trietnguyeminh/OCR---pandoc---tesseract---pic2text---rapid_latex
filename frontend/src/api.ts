// Typed client for the FormuDoc FastAPI backend.

export type ConvertMode = "fast" | "scientific" | "ocr_heavy";

export interface ConvertOptions {
  mode: ConvertMode;
  preserve_layout: boolean;
  detect_formulas: boolean;
  convert_formulas_editable: boolean;
  detect_tables: boolean;
  remove_headers_footers: boolean;
}

export interface AnalyzeResponse {
  file_id: string;
  filename: string;
  size_bytes: number;
  pages: number;
  classification: string;
  scanned_pages: number;
  capabilities: Record<string, boolean>;
  page_info: Array<Record<string, number | boolean>>;
}

export interface ConversionReport {
  pages: number;
  detected_text_blocks: number;
  detected_tables: number;
  detected_formulas: number;
  editable_equations: number;
  image_fallback_equations: number;
  detected_figures: number;
  removed_headers_footers: number;
  classification: string;
  engines_used: Record<string, string>;
  warnings: string[];
}

export interface JobInfo {
  job_id: string;
  status: "queued" | "running" | "done" | "error";
  progress: number;
  stage: string;
  filename: string;
  log: string[];
  report: ConversionReport | null;
  error: string | null;
  download_url: string | null;
  report_url: string | null;
  preview: string | null;
  saved_path: string | null;
}

async function jsonOrThrow(res: Response) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function analyzePdf(file: File): Promise<AnalyzeResponse> {
  const fd = new FormData();
  fd.append("file", file);
  return jsonOrThrow(await fetch("/api/analyze-pdf", { method: "POST", body: fd }));
}

export async function startConvert(
  file_id: string,
  options: ConvertOptions,
  filename?: string,
  apiKeys?: string[]
): Promise<{ job_id: string }> {
  return jsonOrThrow(
    await fetch("/api/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_id, filename, api_keys: apiKeys ?? [], options }),
    })
  );
}

export async function getJob(job_id: string): Promise<JobInfo> {
  return jsonOrThrow(await fetch(`/api/jobs/${job_id}`));
}

export async function checkHealth(): Promise<Record<string, boolean> | null> {
  try {
    const r = await fetch("/health");
    if (!r.ok) return null;
    return (await r.json()).capabilities ?? {};
  } catch {
    return null;
  }
}

export const downloadDocxUrl = (id: string) => `/api/download/${id}`;
export const reportJsonUrl = (id: string) => `/api/report/${id}`;
