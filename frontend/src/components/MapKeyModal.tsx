import { type FormEvent, useEffect, useState } from "react";
import { DriversAPI } from "../api";
import Spinner from "./Spinner";

type Props = { open: boolean; onClose: () => void };

export default function MapKeyModal({ open, onClose }: Props) {
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!open) {
      setKey("");
      setError(null);
    }
  }, [open]);

  if (!open) return null;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const trimmed = key.trim();
    if (!trimmed) {
      setError("Please enter your Mapbox Default public token (pk.xxx).");
      return;
    }
    if (!trimmed.startsWith("pk.")) {
      setError("That doesn't look like a Mapbox public token (should start with pk.).");
      return;
    }
    setSaving(true);
    try {
      await DriversAPI.updateProfile({ mapbox_api_key: trimmed });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h3 className="text-lg font-semibold text-gray-900">Add your Mapbox token</h3>
        <p className="mt-1 text-sm text-gray-600">
          Paste your Mapbox <span className="font-medium">Default public token</span> (starts with
          <code className="mx-1 rounded bg-gray-100 px-1 py-0.5 text-xs">pk.</code>). We store it
          securely and only use it for route requests.
        </p>
        <form onSubmit={submit} className="mt-4 grid gap-3">
          <label className="text-sm font-medium text-gray-700" htmlFor="mapbox-token">
            Mapbox token
          </label>
          <input
            id="mapbox-token"
            placeholder="pk.abcdefghijklmnopqrstuvwxyz1234567890"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm outline-none ring-0 transition focus:border-blue-500"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
          {error && <div className="text-sm text-red-600">{error}</div>}
          <div className="mt-2 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? (
                <>
                  <Spinner size={16} className="text-white" />
                  Saving
                </>
              ) : (
                "Save"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
