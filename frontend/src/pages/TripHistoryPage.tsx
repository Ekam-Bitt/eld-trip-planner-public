import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { TripsAPI, type TripDetail } from "../api";
import Spinner from "../components/Spinner";

type Trip = Pick<
  TripDetail,
  | "id"
  | "pickup_location"
  | "dropoff_location"
  | "distance_miles"
  | "estimated_hours"
  | "created_at"
>;

export default function TripHistoryPage() {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const data = await TripsAPI.list();
        setTrips(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="py-6">
      <h2 className="text-2xl font-bold mb-4">Trip History</h2>
      {error && <div className="bg-red-600 text-white px-4 py-2 rounded-lg mb-3">{error}</div>}
      {loading && (
        <div className="flex items-center gap-2 mb-3">
          <Spinner /> <span>Loading trips…</span>
        </div>
      )}
      <div className="rounded-2xl shadow-lg bg-slate-800 p-4 overflow-x-auto">
        <table className="w-full text-left divide-y divide-slate-700">
          <thead className="bg-slate-800 text-gray-300 uppercase text-xs tracking-wider">
            <tr>
              <th className="px-4 py-2">Created</th>
              <th className="px-4 py-2">Pickup</th>
              <th className="px-4 py-2">Dropoff</th>
              <th className="px-4 py-2">Distance</th>
              <th className="px-4 py-2">ETA (hrs)</th>
              <th className="px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {trips.map((t, idx) => (
              <tr
                key={t.id}
                className={
                  idx % 2 === 0
                    ? "odd:bg-slate-900 hover:bg-slate-700"
                    : "even:bg-slate-800 hover:bg-slate-700"
                }
              >
                <td className="px-4 py-2">
                  <Link className="text-blue-500 hover:underline" to={`/trips/${t.id}`}>
                    {t.created_at.slice(0, 19).replace("T", " ")}
                  </Link>
                </td>
                <td className="px-4 py-2">{t.pickup_location}</td>
                <td className="px-4 py-2">{t.dropoff_location}</td>
                <td className="px-4 py-2">{t.distance_miles} mi</td>
                <td className="px-4 py-2">{t.estimated_hours}</td>
                <td className="px-4 py-2">
                  <button
                    className="p-2 rounded-lg hover:bg-slate-700"
                    onClick={async () => {
                      try {
                        await TripsAPI.remove(t.id);
                        setTrips((prev) => prev.filter((x) => x.id !== t.id));
                      } catch (e) {
                        setError(e instanceof Error ? e.message : String(e));
                      }
                    }}
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                      className="w-5 h-5 text-red-500"
                    >
                      <path
                        fillRule="evenodd"
                        d="M9 3.75A2.25 2.25 0 0111.25 1.5h1.5A2.25 2.25 0 0115 3.75V4.5h3.75a.75.75 0 010 1.5H5.25a.75.75 0 010-1.5H9v-.75zM6.75 7.5h10.5l-.697 11.152A2.25 2.25 0 0114.311 21H9.689a2.25 2.25 0 01-2.242-2.348L6.75 7.5z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
