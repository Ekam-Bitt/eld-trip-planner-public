import { useEffect, useState } from "react";
import { api, type TripDetail } from "../api";

export default function DashboardPage() {
  const [data, setData] = useState<null | {
    cycle: { used_8d: number; remaining_8d: number };
    today: {
      driving: number;
      on_duty: number;
      off: number;
      sleeper: number;
      driving_left: number;
      onduty_left: number;
    };
    warnings: string[];
    recent_trips: Pick<
      TripDetail,
      | "id"
      | "pickup_location"
      | "dropoff_location"
      | "distance_miles"
      | "estimated_hours"
      | "created_at"
    >[];
  }>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const d = await api<NonNullable<typeof data>>("/api/drivers/dashboard/");
        setData(d);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="py-6 grid gap-4">
      <h2 className="text-2xl font-bold">Dashboard</h2>
      {error && <div className="bg-red-600 text-white px-4 py-2 rounded-lg">{error}</div>}
      {loading && <div>Loading…</div>}
      {data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card
              title="Driving Today"
              value={`${data.today.driving.toFixed(2)} h`}
              sub={`Left: ${data.today.driving_left.toFixed(2)} h`}
            />
            <Card
              title="On-duty Today"
              value={`${data.today.on_duty.toFixed(2)} h`}
              sub={`Left: ${data.today.onduty_left.toFixed(2)} h`}
            />
            <Card
              title="Cycle (8-day)"
              value={`${data.cycle.used_8d.toFixed(2)} / 70 h`}
              sub={`Remaining: ${data.cycle.remaining_8d.toFixed(2)} h`}
            />
          </div>
          {data.warnings.length > 0 && (
            <div className="border border-yellow-500/40 bg-yellow-500/10 text-yellow-300 rounded-xl p-4">
              <div className="font-semibold mb-2">Warnings</div>
              <ul className="list-disc pl-6">
                {data.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="grid gap-2">
            <div className="text-lg font-semibold">Recent Trips</div>
            <div className="rounded-2xl shadow-lg bg-slate-800 p-4 overflow-x-auto">
              <table className="w-full text-left divide-y divide-slate-700">
                <thead className="text-gray-300 uppercase text-xs tracking-wider">
                  <tr>
                    <th className="px-4 py-2">Created</th>
                    <th className="px-4 py-2">Pickup</th>
                    <th className="px-4 py-2">Dropoff</th>
                    <th className="px-4 py-2">Distance</th>
                    <th className="px-4 py-2">ETA (hrs)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_trips.map((t) => (
                    <tr key={t.id}>
                      <td className="px-4 py-2">{t.created_at.slice(0, 19).replace("T", " ")}</td>
                      <td className="px-4 py-2">{t.pickup_location}</td>
                      <td className="px-4 py-2">{t.dropoff_location}</td>
                      <td className="px-4 py-2">{t.distance_miles} mi</td>
                      <td className="px-4 py-2">{t.estimated_hours}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Card({ title, value, sub }: { title: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl shadow-lg bg-slate-800 p-6 border border-slate-700">
      <div className="text-sm text-gray-400">{title}</div>
      <div className="text-3xl font-extrabold">{value}</div>
      {sub && <div className="text-sm text-gray-400 mt-1">{sub}</div>}
    </div>
  );
}
