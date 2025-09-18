import { type FormEvent, useEffect, useState } from "react";
import { DriversAPI } from "../api";

type Props = { open: boolean; onClose: () => void };

export default function MapKeyModal({ open, onClose }: Props) {
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
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
    try {
      await DriversAPI.updateProfile({ mapbox_api_key: key });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "#0006",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div style={{ background: "white", padding: 16, borderRadius: 8, minWidth: 360 }}>
        <h3>Enter Mapbox API key</h3>
        <p>We use your key to fetch routes. It's encrypted at rest.</p>
        <form onSubmit={submit} style={{ display: "grid", gap: 8 }}>
          <input
            placeholder="Mapbox API key"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button type="button" onClick={onClose}>
              Cancel
            </button>
            <button type="submit">Save</button>
          </div>
          {error && <div style={{ color: "red" }}>{error}</div>}
        </form>
      </div>
    </div>
  );
}
