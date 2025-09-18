const API_BASE =
  import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE || "http://localhost:8000";

export type DriverMe = {
  id: number;
  name: string;
  email: string;
  license_no: string;
  license_state?: string | null;
  truck_type?: string;
  truck_number?: string | null;
  avg_mpg?: number | null;
  carrier_name?: string | null;
  terminal_name?: string | null;
  time_zone?: string;
  units?: "miles" | "km";
  dark_mode?: boolean;
  date_joined: string;
  has_mapbox_key: boolean;
  profile?: {
    license_state?: string;
    driver_initials?: string;
    driver_signature?: string;
    home_center_city?: string;
    home_center_state?: string;
    carrier?: string;
    time_zone?: string;
    units?: "MILES" | "KM";
  };
};

export type TripDetail = {
  id: number;
  current_location: string;
  pickup_location: string;
  dropoff_location: string;
  distance_miles: number;
  estimated_hours: number;
  fueling_stops: { mile?: number; coord?: [number, number] }[];
  pickup_time?: string | null;
  dropoff_time?: string | null;
  route_geometry: { type: "LineString"; coordinates: [number, number][] };
  route_metadata?: {
    distance?: number;
    duration?: number;
    legs?: { steps?: { distance?: number; maneuver?: { instruction?: string } }[] }[];
  };
  created_at: string;
};

export type LogStatus = "OFF" | "SLEEPER" | "DRIVING" | "ON_DUTY";

export type LogEvent = {
  id: number;
  trip: number;
  driver: number;
  day: string; // YYYY-MM-DD
  timestamp: string; // ISO
  status: LogStatus;
  city?: string;
  state?: string;
  activity?: string;
  created_at: string;
};

export async function api<T = unknown>(path: string, opts: RequestInit = {}): Promise<T> {
  const access = localStorage.getItem("access");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (access) headers["Authorization"] = `Bearer ${access}`;
  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    let detail = "Request failed";
    try {
      const data = (await res.json()) as { detail?: string } | unknown;
      if (data && typeof data === "object" && "detail" in (data as Record<string, unknown>)) {
        detail = String((data as { detail?: unknown }).detail ?? detail);
      } else {
        detail = JSON.stringify(data);
      }
    } catch {
      // keep default detail
    }
    throw new Error(detail);
  }
  // Handle empty responses (e.g., 204 No Content from DELETE)
  if (res.status === 204) return undefined as T;
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const text = await res.text();
    // If server returned empty body, treat as void
    if (!text) return undefined as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      // Fallback: return as unknown text
      return text as unknown as T;
    }
  }
  return (await res.json()) as T;
}

export const DriversAPI = {
  me: () => api<DriverMe>("/api/drivers/me/"),
  updateProfile: (payload: Partial<{
    mapbox_api_key: string;
    name: string;
    license_no: string;
    license_state: string;
    truck_type: string;
    truck_number: string;
    avg_mpg: number;
    carrier_name: string;
    terminal_name: string;
    time_zone: string;
    units: "miles" | "km";
    dark_mode: boolean;
  }> ) => api("/api/drivers/profile/", { method: "PUT", body: JSON.stringify(payload) }),
};

export const TripsAPI = {
  create: (payload: Record<string, unknown>) =>
    api<TripDetail>("/api/trips/", { method: "POST", body: JSON.stringify(payload) }),
  list: () => api<TripDetail[]>("/api/trips/"),
  detail: (id: number) => api<TripDetail>(`/api/trips/${id}/`),
  update: (id: number, payload: Record<string, unknown>) => api<TripDetail>(`/api/trips/${id}/`, { method: "PATCH", body: JSON.stringify(payload) }),
  remove: (id: number) => api<void>(`/api/trips/${id}/`, { method: "DELETE" }),
};

export const LogsAPI = {
  create: (trip_id: number, status: LogStatus, timestamp?: string, remark?: { city?: string; state?: string; activity?: string }) =>
    api<LogEvent>("/api/logs/", {
      method: "POST",
      body: JSON.stringify({ trip_id, status, ...(timestamp ? { timestamp } : {}), ...(remark || {}) }),
    }),
  list: (trip_id: number) => api<LogEvent[]>(`/api/logs/${trip_id}/`),
  hos: (trip_id: number) => api<{ daily: { day: string; totals: Record<string, number> }[]; violations: { code: string; message: string; day: string }[] }>(`/api/logs/${trip_id}/hos/`),
  dailyList: (trip_id: number) => api(`/api/logs/${trip_id}/daily/`),
  submitDay: (trip_id: number, day: string) => api(`/api/logs/${trip_id}/daily/submit/`, { method: "POST", body: JSON.stringify({ day }) }),
};

export type Inspection = {
  id: number;
  trip: number;
  driver: number;
  kind: "PRE_TRIP" | "POST_TRIP";
  performed_at: string;
  defects: { item: string; severity?: string; note?: string }[];
  signature_driver: string;
  signature_mechanic?: string;
  notes?: string;
  created_at: string;
};

export const InspectionsAPI = {
  create: (payload: { trip_id: number; kind: "PRE_TRIP" | "POST_TRIP"; performed_at?: string; defects?: Inspection["defects"]; signature_driver: string; signature_mechanic?: string; notes?: string }) =>
    api<Inspection>("/api/logs/inspections/", { method: "POST", body: JSON.stringify(payload) }),
  list: (trip_id: number) => api<Inspection[]>(`/api/logs/${trip_id}/inspections/`),
};

export const ReportsAPI = {
  pdfUrl: (trip_id: number) => `${API_BASE}/api/reports/trip/${trip_id}/pdf/`,
  csvUrl: (trip_id: number) => `${API_BASE}/api/reports/trip/${trip_id}/csv/`,
};
