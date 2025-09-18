import { useState } from "react";
import { LogsAPI, type LogEvent, type LogStatus } from "../api";

type Props = { tripId: number; onLogged?: () => void; onLoggedEvent?: (ev: LogEvent) => void };

const STATUSES: LogStatus[] = ["OFF", "SLEEPER", "DRIVING", "ON_DUTY"];

export default function LogControls({ tripId, onLogged, onLoggedEvent }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function setStatus(status: LogStatus) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const ev = await LogsAPI.create(tripId, status);
      onLoggedEvent?.(ev);
      onLogged?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex gap-2 items-center flex-wrap">
      {STATUSES.map((s) => (
        <button
          key={s}
          onClick={() => setStatus(s)}
          disabled={busy}
          className={`px-4 py-2 rounded-lg font-semibold shadow ${
            s === "DRIVING" ? "bg-blue-600 hover:bg-blue-500 text-white" : "bg-slate-700 hover:bg-slate-600"
          }`}
        >
          {s.replace("_", " ")}
        </button>
      ))}
      {error && <span className="text-red-400 text-sm">{error}</span>}
    </div>
  );
}




