export const API_BASE = "/backend";

export type SessionUser = {
  email: string;
  full_name: string;
  role: string;
};

export type DemoAccount = {
  email: string;
  password: string;
  full_name: string;
  role: string;
};

export type DirectoryUser = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  locale: string;
  is_active: boolean;
  created_at: string;
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("vs_token");
}

export function getSession(): SessionUser | null {
  if (typeof window === "undefined" || !getToken()) return null;
  return {
    email: localStorage.getItem("vs_email") || "",
    full_name: localStorage.getItem("vs_name") || "",
    role: localStorage.getItem("vs_role") || "",
  };
}

export function isAdmin(): boolean {
  return getSession()?.role === "admin";
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("vs_token");
  localStorage.removeItem("vs_role");
  localStorage.removeItem("vs_email");
  localStorage.removeItem("vs_name");
}

export function roleLabel(role: string): string {
  if (role === "admin") return "Administrador";
  if (role === "analyst") return "Analista";
  if (role === "viewer") return "Consulta";
  if (role === "mobile") return "Móvil";
  return role;
}

export function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function authBlob(path: string): Promise<string> {
  const response = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
  if (!response.ok) throw new Error("No se pudo cargar el archivo");
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams({ username: email, password });
  const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) {
    let detail = "No se pudo iniciar sesión";
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      if (response.status === 401) detail = "Usuario o clave incorrectos";
      else if (response.status >= 500) detail = "El servidor no pudo procesar el acceso";
    }
    throw new Error(detail);
  }
  const data = await response.json();
  localStorage.setItem("vs_token", data.access_token);
  localStorage.setItem("vs_role", data.role || "");
  localStorage.setItem("vs_email", data.email || email);
  localStorage.setItem("vs_name", data.full_name || "");
  return data.access_token;
}

export type DashboardMetrics = {
  sessions_total: number;
  analyses_completed: number;
  analyses_failed: number;
  analyses_in_progress: number;
  avg_reliability: number;
  avg_deception: number;
  celery_workers: number;
  celery_active_tasks: number;
  celery_queued_tasks: number;
};

export type ClipWindow = {
  index: number;
  window_start: number;
  window_end: number;
  duration: number;
  samples: number[];
  start: number;
  end: number;
  answer_start: number;
  answer_end: number;
};

export type InterviewExchange = {
  index: number;
  question: string;
  answer: string;
  start: number;
  end: number;
  duration: number;
  answer_start?: number;
  answer_end?: number;
  samples: number[];
  spectrum_mags?: number[];
  spectrum_duration?: number;
  spectrum_fmax?: number;
  spectrum_peak_hz?: number;
  spectrum_band_lo?: number;
  spectrum_band_hi?: number;
  comb_samples?: number[];
  comb_duration?: number;
  comb_band_lo?: number;
  comb_band_hi?: number;
  include_vsa_in_report?: boolean;
  include_comb_in_report?: boolean;
  vsa_report_note?: string;
  comb_report_note?: string;
  vsa_report_note_color?: string;
  comb_report_note_color?: string;
  kind?: string;
  kind_label?: string;
  vsa_score?: number;
  fm_stress?: number;
  fm_8_12_ratio?: number;
  delta?: number;
  flagged?: boolean;
};

export type VsaItem = {
  index: number;
  kind: string;
  kind_label: string;
  question: string;
  answer: string;
  vsa_score: number;
  fm_stress?: number;
  fm_8_12_ratio?: number;
  delta: number;
  flagged: boolean;
};

export type VsaSummary = {
  baseline: number;
  vsa_index: number;
  flagged_count: number;
  control_count: number;
  stimulus_count: number;
  relevant_count: number;
  note?: string;
  items?: VsaItem[];
};

export type ExamFicha = {
  evaluation_code?: string | null;
  title?: string | null;
  subject_name?: string | null;
  subject_document?: string | null;
  location?: string | null;
  modality?: string | null;
  purpose?: string | null;
  evaluator_name?: string | null;
  evaluator_title?: string | null;
};

export type InterviewTurn = {
  role: string;
  label: string;
  text: string;
  start: number;
  end: number;
};

export type Report = {
  id: string;
  session_id: string;
  audio_record_id: string;
  transcription: string | null;
  language_detected: string;
  stt_engine: string | null;
  linguistic_score: number;
  acoustic_score: number;
  deception_index: number;
  reliability_index: number;
  findings: {
    summary?: string;
    disclaimer?: string;
    risk_band?: string;
    acoustic_engine?: string;
    method?: string;
    interview?: {
      has_dialogue?: boolean;
      transcript_dialogo?: string;
      turns?: InterviewTurn[];
      exchanges?: InterviewExchange[];
      waveform?: {
        duration: number;
        sample_rate: number;
        samples: number[];
        spectrum_mags?: number[];
        spectrum_duration?: number;
        spectrum_fmax?: number;
        spectrum_peak_hz?: number;
        spectrum_band_lo?: number;
        spectrum_band_hi?: number;
      };
    };
    acoustic_features?: {
      praat?: boolean;
      acoustic_engine?: string;
      pitch_mean_hz?: number | null;
      pitch_std_hz?: number | null;
      hnr_mean_db?: number | null;
      jitter_local?: number | null;
      shimmer_local?: number | null;
      intensity_mean_db?: number | null;
      formant_f1_hz?: number | null;
      formant_f2_hz?: number | null;
      voiced_pulses?: number | null;
      note?: string;
    };
    findings?: Array<{
      code: string;
      title: string;
      detail: string;
      severity: string;
      evidence?: string;
    }>;
    exam?: ExamFicha;
    vsa?: VsaSummary;
  };
  created_at: string;
};

export type AnalyzeAccepted = {
  audio_id: string;
  session_id: string;
  task_id: string;
  status: string;
  message: string;
};

export type ProgressStage = {
  percent: number;
  status: "pending" | "running" | "done" | "error" | string;
  label: string;
};

export type AnalysisProgress = {
  conversion: ProgressStage;
  transcription: ProgressStage;
  analysis: ProgressStage;
};

export type AnalyzeStatus = {
  audio: { id: string; status: string; original_name: string; celery_task_id: string | null };
  task_state: string | null;
  report: Report | null;
  progress?: AnalysisProgress | null;
};

export type Health = {
  status: string;
  version: string;
  processing_mode: string;
  locale: string;
  components: Array<{ name: string; status: string; detail?: string }>;
};
