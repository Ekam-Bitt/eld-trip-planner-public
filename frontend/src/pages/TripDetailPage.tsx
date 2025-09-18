import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "react-toastify";
import { useParams, Link } from "react-router-dom";
import { LogsAPI, TripsAPI, type LogEvent, type TripDetail, ReportsAPI } from "../api";
import Spinner from "../components/Spinner";
// import MapDisplay from "../components/MapDisplay";
import LogGraph from "../components/LogGraph";

type TripHeaderKeys =
  | "log_date"
  | "co_driver_name"
  | "tractor_number"
  | "trailer_numbers"
  | "other_trailers"
  | "shipper_name"
  | "commodity_description"
  | "load_id"
  | "total_miles_driving_today"
  | "total_mileage_today";

type ExtendedTrip = TripDetail & Partial<Record<TripHeaderKeys, string>>;

export default function TripDetailPage() {
  const { id } = useParams();
  const tripId = useMemo(() => (id ? Number(id) : NaN), [id]);
  const [trip, setTrip] = useState<TripDetail | null>(null);
  const [events, setEvents] = useState<LogEvent[]>([]);
  // const [violations, setViolations] = useState<{ code: string; message: string; day: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [remarks, setRemarks] = useState<
    { timestamp: string; city: string; state: string; activity: string }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [graphSize, setGraphSize] = useState<{ w: number; h: number }>({ w: 1280, h: 320 });

  // Refs to day graphs for rasterization
  const dayGraphRefs = useRef<Record<string, SVGSVGElement | null>>({});

  // Ensure SVG refs are captured after render
  useEffect(() => {
    const days = [...new Map(events.map((e) => [e.day, true])).keys()];
    console.log(`SVG capture useEffect: found ${days.length} days:`, days);

    const timer = setTimeout(() => {
      days.forEach((day) => {
        const container = document.querySelector(`[data-day="${day}"]`);
        if (container) {
          const svg = container.querySelector("svg");
          if (svg) {
            if (typeof window !== "undefined") {
              window.__dayGraphRefs = window.__dayGraphRefs || {};
              window.__dayGraphRefs[day] = svg;
              dayGraphRefs.current[day] = svg;
              console.log(`Captured SVG for day ${day}:`, !!svg);
            }
          } else {
            console.log(`No SVG found in container for day ${day}`);
          }
        } else {
          console.log(`No container found for day ${day}`);
        }
      });

      // Also try a more aggressive approach - find all SVGs in the page
      const allSvgs = document.querySelectorAll("svg");
      console.log(`Found ${allSvgs.length} total SVGs on page`);
    }, 100); // Small delay to ensure SVGs are rendered

    return () => clearTimeout(timer);
  }, [events, graphSize]);

  // Trip header edit state
  const [editingTripHeader, setEditingTripHeader] = useState(false);
  const [tripHeader, setTripHeader] = useState<Record<TripHeaderKeys, string>>({
    log_date: "",
    co_driver_name: "",
    tractor_number: "",
    trailer_numbers: "",
    other_trailers: "",
    shipper_name: "",
    commodity_description: "",
    load_id: "",
    total_miles_driving_today: "",
    total_mileage_today: "",
  });

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0]?.contentRect;
      if (!cr) return;
      const w = Math.max(640, Math.floor(cr.width));
      const h = Math.max(260, Math.floor(w / 4));
      setGraphSize({ w, h });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  async function load() {
    if (!Number.isFinite(tripId)) return;
    setLoading(true);
    setError(null);
    try {
      const [t, e] = await Promise.all([
        TripsAPI.detail(tripId),
        LogsAPI.list(tripId),
      ]);
      setTrip(t);
      setEvents(e);
      const xt = t as ExtendedTrip;
      setTripHeader({
        log_date: xt.log_date ? xt.log_date.slice(0, 10) : "",
        co_driver_name: xt.co_driver_name || "",
        tractor_number: xt.tractor_number || "",
        trailer_numbers: xt.trailer_numbers || "",
        other_trailers: xt.other_trailers || "",
        shipper_name: xt.shipper_name || "",
        commodity_description: xt.commodity_description || "",
        load_id: xt.load_id || "",
        total_miles_driving_today: xt.total_miles_driving_today || "",
        total_mileage_today: xt.total_mileage_today || "",
      });
      try {
        const stored = localStorage.getItem(`tripRemarks:${tripId}`);
        if (stored) setRemarks(JSON.parse(stored));
      } catch {
        // ignore
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId]);

  // const parseCoord = (s?: string): [number, number] | undefined => {
  //   if (!s) return undefined;
  //   const parts = s.split(",").map((x) => Number(x.trim()));
  //   if (parts.length !== 2 || parts.some((n) => Number.isNaN(n))) return undefined;
  //   return [parts[0], parts[1]];
  // };

  // Inspection form state
  // const inspectFormRef = useRef<HTMLFormElement | null>(null);
  // const [defects, setDefects] = useState<{ item: string; severity?: string; note?: string }[]>([]);

  // async function submitInspection(e: React.FormEvent<HTMLFormElement>) {
  //   e.preventDefault();
  //   const formEl = e.currentTarget;
  //   const fd = new FormData(formEl);
  //   const kind = String(fd.get("kind") || "PRE_TRIP") as "PRE_TRIP" | "POST_TRIP";
  //   const signature_driver = String(fd.get("signature_driver") || "");
  //   const notes = String(fd.get("notes") || "");
  //   try {
  //     await InspectionsAPI.create({ trip_id: tripId, kind, signature_driver, notes, defects });
  //     await load();
  //     setDefects([]);
  //     if (formEl) formEl.reset();
  //   } catch (err) {
  //     setError(err instanceof Error ? err.message : String(err));
  //   }
  // }

  async function saveTripHeader() {
    if (!trip) return;
    try {
      await TripsAPI.update(trip.id, {
        ...tripHeader,
        total_miles_driving_today: tripHeader.total_miles_driving_today || null,
        total_mileage_today: tripHeader.total_mileage_today || null,
      });
      await load();
      setEditingTripHeader(false);
      toast.success("Trip details saved");
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      toast.error(msg);
    }
  }

  // Simplified SVG to PNG conversion and POST to server
  async function exportPdfWithGraphs() {
    setError(null);
    try {
      console.log("=== Simplified PDF Export ===");

      // Find any SVG on the page (simplified approach)
      const allSvgs = document.querySelectorAll("svg");
      console.log(`Found ${allSvgs.length} SVGs on page`);

      const graphs: { day: string; png: string }[] = [];

      if (allSvgs.length > 0) {
        // Use the first SVG we find (assuming it's the log graph)
        const svg = allSvgs[0] as SVGSVGElement;
        const today = new Date().toISOString().slice(0, 10);
        console.log(`Using SVG for date ${today}`);

        try {
          const svgData = new XMLSerializer().serializeToString(svg);
          console.log(`SVG data length: ${svgData.length}`);

          const svgBlob = new Blob([svgData], { type: "image/svg+xml;charset=utf-8" });
          const url = URL.createObjectURL(svgBlob);

          const img = await new Promise<HTMLImageElement>((resolve, reject) => {
            const i = new Image();
            i.onload = () => resolve(i);
            i.onerror = (e) => {
              console.error("Image load error:", e);
              reject(e);
            };
            i.src = url;
          });

          const canvas = document.createElement("canvas");
          canvas.width = img.naturalWidth || svg.clientWidth || 1280;
          canvas.height = img.naturalHeight || svg.clientHeight || 320;
          console.log(`Canvas dimensions: ${canvas.width}x${canvas.height}`);

          const ctx = canvas.getContext("2d");
          if (!ctx) throw new Error("Canvas 2D not supported");

          ctx.drawImage(img, 0, 0);
          const png = canvas.toDataURL("image/png");
          console.log(`Generated PNG, size: ${png.length} chars`);

          graphs.push({ day: today, png });
          URL.revokeObjectURL(url);
        } catch (svgErr) {
          console.error("Error processing SVG:", svgErr);
        }
      } else {
        console.log("No SVGs found on page");
      }

      console.log(`Final graphs array: ${graphs.length} items`);

      const access = localStorage.getItem("access");
      const res = await fetch(ReportsAPI.pdfUrl(tripId), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: access ? `Bearer ${access}` : "",
        },
        body: JSON.stringify({ graphs }),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = `trip_${tripId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
      toast.success("PDF exported");
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      toast.error(msg);
    }
  }

  return (
    <div style={{ padding: 16, display: "grid", gap: 16 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <Link to="/trips">← Back to Trips</Link>
        <h3 style={{ margin: 0 }}>Trip {tripId}</h3>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button className="btn" onClick={exportPdfWithGraphs}>
            Export PDF
          </button>
          <button
            className="btn"
            onClick={() => download(ReportsAPI.csvUrl(tripId), `trip_${tripId}.csv`)}
          >
            Export CSV
          </button>
        </div>
      </div>
      {error && <div style={{ color: "red" }}>{error}</div>}
      {loading && (
        <div className="flex items-center gap-2">
          <Spinner /> <span>Loading trip…</span>
        </div>
      )}
      {trip && (
        <>
          {/* Trip header view/edit */}
          <div className="border border-gray-800 rounded-lg p-4 bg-gray-900">
            <div className="flex items-center justify-between mb-2">
              <div className="font-semibold">Trip Details</div>
              <button
                className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600"
                onClick={() => setEditingTripHeader((v) => !v)}
              >
                {editingTripHeader ? "Cancel" : "Edit"}
              </button>
            </div>
            {editingTripHeader ? (
              <div className="grid md:grid-cols-3 gap-3">
                {(
                  [
                    ["Log Date", "log_date", "date"],
                    ["Co-driver", "co_driver_name", "text"],
                    ["Tractor #", "tractor_number", "text"],
                    ["Trailer #s", "trailer_numbers", "text"],
                    ["Other Trailers", "other_trailers", "text"],
                    ["Shipper", "shipper_name", "text"],
                    ["Commodity", "commodity_description", "text"],
                    ["Load ID", "load_id", "text"],
                    ["Total Miles Driving Today", "total_miles_driving_today", "text"],
                    ["Total Mileage Today", "total_mileage_today", "text"],
                  ] as Array<[string, TripHeaderKeys, "text" | "date"]>
                ).map(([label, key, type]) => (
                  <label key={key} className="text-sm grid gap-1">
                    <span>{label}</span>
                    <input
                      type={type}
                      className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white"
                      value={tripHeader[key] || ""}
                      onChange={(e) =>
                        setTripHeader((h) => ({ ...h, [key]: e.target.value }))
                      }
                    />
                  </label>
                ))}
                <div className="col-span-full">
                  <button
                    className="px-4 py-2 rounded bg-indigo-600 hover:bg-indigo-500"
                    onClick={saveTripHeader}
                  >
                    Save
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid md:grid-cols-4 gap-2 text-sm text-gray-200">
                <div>
                  <span className="text-gray-400">Log Date:</span> {(trip as ExtendedTrip).log_date || "—"}
                </div>
                <div>
                  <span className="text-gray-400">Co-driver:</span>{" "}
                  {(trip as ExtendedTrip).co_driver_name || "—"}
                </div>
                <div>
                  <span className="text-gray-400">Tractor #:</span>{" "}
                  {(trip as ExtendedTrip).tractor_number || "—"}
                </div>
                <div>
                  <span className="text-gray-400">Trailer #s:</span>{" "}
                  {(trip as ExtendedTrip).trailer_numbers || (trip as ExtendedTrip).other_trailers || "—"}
                </div>
                <div>
                  <span className="text-gray-400">Miles Driving Today:</span>{" "}
                  {(trip as ExtendedTrip).total_miles_driving_today || "—"}
                </div>
                <div>
                  <span className="text-gray-400">Total Mileage Today:</span>{" "}
                  {(trip as ExtendedTrip).total_mileage_today || "—"}
                </div>
                <div>
                  <span className="text-gray-400">Shipper:</span>{" "}
                  {(trip as ExtendedTrip).shipper_name || "—"}
                </div>
                <div>
                  <span className="text-gray-400">Commodity:</span>{" "}
                  {(trip as ExtendedTrip).commodity_description || "—"}
                </div>
                <div>
                  <span className="text-gray-400">Load ID:</span> {(trip as ExtendedTrip).load_id || "—"}
                </div>
              </div>
            )}
          </div>

          <div ref={wrapRef} style={{ display: "grid", gap: 12 }}>
            {[...new Map(events.map((e) => [e.day, true])).keys()].map((day) => (
              <div key={day} style={{ display: "grid", gap: 8 }}>
                <div className="text-sm text-gray-300">{day}</div>
                <div
                  data-day={day}
                  ref={(el) => {
                    // Capture SVG ref when container is mounted
                    if (el) {
                      const svg = el.querySelector("svg");
                      if (svg) {
                        if (typeof window !== "undefined") {
                          window.__dayGraphRefs = window.__dayGraphRefs || {};
                          window.__dayGraphRefs[day] = svg;
                          // Also update our React ref
                          dayGraphRefs.current[day] = svg;
                        }
                      }
                    }
                  }}
                >
                  <LogGraph
                    events={events.filter((e) => e.day === day)}
                    remarks={remarks.filter((r) => r.timestamp.slice(0, 10) === day)}
                    width={graphSize.w}
                    height={graphSize.h}
                    seedMidnightOff={true}
                    squareCells={true}
                  />
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

declare global {
  interface Window {
    __dayGraphRefs?: Record<string, SVGSVGElement | null>;
  }
}

  // Before export, sync window refs to react ref
  // function syncGraphRefs(ref: React.MutableRefObject<Record<string, SVGSVGElement | null>>) {
  //   if (typeof window !== "undefined" && window.__dayGraphRefs) {
  //     ref.current = window.__dayGraphRefs;
  //   }
  // }

async function download(url: string, filename: string) {
  const access = localStorage.getItem("access");
  const res = await fetch(url, { headers: access ? { Authorization: `Bearer ${access}` } : {} });
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}
