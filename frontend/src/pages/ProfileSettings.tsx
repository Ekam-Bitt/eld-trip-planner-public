import { type FormEvent, useEffect, useState } from "react";
import { toast } from "react-toastify";
import { DriversAPI, type DriverMe } from "../api";

export default function ProfileSettings() {
  const [me, setMe] = useState<DriverMe | null>(null);
  const [form, setForm] = useState({
    name: "",
    license_no: "",
    license_state: "",
    avg_mpg: "",
    terminal_name: "",
    time_zone: "UTC",
    units: "miles" as "miles" | "km",
    mapbox_api_key: "",
  });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await DriversAPI.me();
        setMe(data);
        setForm({
          name: data.name,
          license_no: data.license_no,
          license_state: data.license_state || "",
          avg_mpg: data.avg_mpg != null ? String(data.avg_mpg) : "",
          terminal_name: (data.terminal_name as string) || "",
          time_zone: data.time_zone || "UTC",
          units: (data.units as "miles" | "km") || "miles",
          mapbox_api_key: "",
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load profile");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        name: form.name,
        license_no: form.license_no,
        license_state: form.license_state,
        avg_mpg: form.avg_mpg ? Number(form.avg_mpg) : undefined,
        terminal_name: form.terminal_name,
        time_zone: form.time_zone,
        units: form.units,
      };
      const key = form.mapbox_api_key.trim();
      if (key) payload["mapbox_api_key"] = key;
      await DriversAPI.updateProfile(payload);
      setSaved(true);
      toast.success("Profile updated");
      setForm((f) => ({ ...f, mapbox_api_key: "" }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      toast.error(msg);
    }
  }

  return (
    <div className="py-6">
      <h3 className="text-xl font-semibold mb-4">Driver Profile</h3>
      {loading ? (
        <div>Loading profile…</div>
      ) : (
        <form onSubmit={onSubmit} className="grid gap-3 max-w-xl">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="font-semibold">Name</label>
              <input className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700" value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            </div>
            <div>
              <label className="font-semibold">License #</label>
              <input className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700" value={form.license_no}
                onChange={(e) => setForm((f) => ({ ...f, license_no: e.target.value }))} />
            </div>
            <div>
              <label className="font-semibold">License State</label>
              <input className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700" value={form.license_state}
                onChange={(e) => setForm((f) => ({ ...f, license_state: e.target.value }))} />
            </div>
            <div>
              <label className="font-semibold">Avg MPG</label>
              <input type="number" step="0.01" className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700" value={form.avg_mpg}
                onChange={(e) => setForm((f) => ({ ...f, avg_mpg: e.target.value }))} />
            </div>
            <div>
              <label className="font-semibold">Terminal</label>
              <input className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700" value={form.terminal_name}
                onChange={(e) => setForm((f) => ({ ...f, terminal_name: e.target.value }))} />
            </div>
            <div>
              <label className="font-semibold">Time Zone</label>
              <input className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700" value={form.time_zone}
                onChange={(e) => setForm((f) => ({ ...f, time_zone: e.target.value }))} />
            </div>
            <div>
              <label className="font-semibold">Units</label>
              <select className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700" value={form.units}
                onChange={(e) => setForm((f) => ({ ...f, units: e.target.value as "miles" | "km" }))}>
                <option value="miles">Miles</option>
                <option value="km">Kilometers</option>
              </select>
            </div>
          </div>
          <label htmlFor="mapboxKey" className="font-semibold">
            Mapbox API key
          </label>
          <input
            className="w-full px-3 py-2 rounded bg-gray-800 border border-gray-700"
            placeholder={me?.has_mapbox_key ? "Key set — enter to replace" : "Enter Mapbox key"}
            value={form.mapbox_api_key}
            onChange={(e) => setForm((f) => ({ ...f, mapbox_api_key: e.target.value }))}
          />
          <div className="text-gray-400 text-sm">
            Your key is stored encrypted at rest. Only this field is editable here.
          </div>
          <div className="flex gap-3">
            <button
              type="submit"
              disabled={false}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50"
            >
              Save
            </button>
          </div>
          {saved && <div className="text-green-400 text-sm">Saved!</div>}
          {error && <div className="text-red-400 text-sm">{error}</div>}
        </form>
      )}
    </div>
  );
}
