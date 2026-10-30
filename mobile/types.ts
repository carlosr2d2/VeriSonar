export type MobilePlatform = "android" | "ios" | "web" | "windows";

export type AnalyzeAccepted = {
  audio_id: string;
  session_id: string;
  task_id: string;
  status: string;
  message: string;
};

export const MOBILE_API_PREFIX = "/api/mobile/v1";
