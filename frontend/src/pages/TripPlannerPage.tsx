import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { TripsAPI, api } from "../api";
import MapDisplay from "../components/MapDisplay";
import DirectionsSidebar from "../components/DirectionsSidebar";
import LogGraph from "../components/LogGraph";
import { LogsAPI, type LogEvent, type LogStatus } from "../api";

type Trip = {
  id: number;
  current_location: string;
  pickup_location: string;
  dropoff_location: string;
  distance_miles: number;
  estimated_hours: number;
  fueling_stops: { mile?: number; coord?: [number, number] }[];
  route_geometry: { type: "LineString"; coordinates: [number, number][] };
  route_metadata?: {
    distance?: number;
    duration?: number;
    legs?: { steps?: { distance?: number; maneuver?: { instruction?: string } }[] }[];
  };
};

function parseCoord(input: string): [number, number] | undefined {
  const parts = input.split(",").map((p) => parseFloat(p.trim()));
  if (parts.length === 2 && parts.every((n) => !Number.isNaN(n))) {
    return [parts[0], parts[1]];
  }
  return undefined;
}

export default function TripPlannerPage() {
  // Default values for quick testing
  const [currentLocation, setCurrentLocation] = useState("-118.2437,34.0522"); // Los Angeles
  const [pickupLocation, setPickupLocation] = useState("-115.1398,36.1699"); // Las Vegas
  const [dropoffLocation, setDropoffLocation] = useState("-104.9903,39.7392"); // Denver
  const [currentCycleUsedHrs, setCurrentCycleUsedHrs] = useState("10");
  // Trip-specific header fields
  const [logDate, setLogDate] = useState<string>(new Date().toISOString().slice(0, 10));
  const [coDriverName, setCoDriverName] = useState<string>("N/A");
  const [tractorNumber, setTractorNumber] = useState<string>("");
  const [trailerNumbers, setTrailerNumbers] = useState<string>("");
  const [otherTrailers, setOtherTrailers] = useState<string>("");
  const [shipperName, setShipperName] = useState<string>("");
  const [commodityDescription, setCommodityDescription] = useState<string>("");
  const [loadId, setLoadId] = useState<string>("");
  const [trip, setTrip] = useState<Trip | null>(null);
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [remarks, setRemarks] = useState<
    { timestamp: string; city: string; state: string; activity: string }[]
  >([]);
  const [remarkModal, setRemarkModal] = useState<
    { open: true; ts: string; defaultActivity: string } | { open: false }
  >({ open: false });
  const [error, setError] = useState<string | null>(null);
  const graphWrapRef = useRef<HTMLDivElement | null>(null);
  const [graphSize, setGraphSize] = useState<{ w: number; h: number }>({ w: 1280, h: 320 });
  const [saving, setSaving] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [manualModal, setManualModal] = useState<
    | { open: true; status: LogStatus; defaultActivity: string; defaultTime: string; defaultDate?: string }
    | { open: false }
  >({ open: false });
  const [pending, setPending] = useState<{ timestamp: string; status: LogStatus }[]>([]);

  const combinedEvents = useMemo((): LogEvent[] => {
    const pendAsEvents: LogEvent[] = pending.map((p, idx) => {
      const dayFromTs = p.timestamp.slice(0, 10);
      return {
        id: (logs[logs.length - 1]?.id || 0) + idx + 1,
        trip: trip?.id || 0,
        driver: 0,
        day: dayFromTs,
        timestamp: p.timestamp,
        status: p.status,
        created_at: p.timestamp,
      } as LogEvent;
    });
    return [...logs, ...pendAsEvents].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  }, [logs, pending, trip?.id]);

  // Persist remarks per trip to localStorage and load on trip change
  useEffect(() => {
    if (!trip?.id) return;
    try {
      const key = `tripRemarks:${trip.id}`;
      const existing = localStorage.getItem(key);
      if (existing) {
        const parsed = JSON.parse(existing) as typeof remarks;
        setRemarks(parsed);
      }
    } catch {
      // ignore
    }
  }, [trip?.id]);
  useEffect(() => {
    if (!trip?.id) return;
    try {
      const key = `tripRemarks:${trip.id}`;
      localStorage.setItem(key, JSON.stringify(remarks));
    } catch {
      // ignore
    }
  }, [remarks, trip?.id]);

  // Day navigation for multi-day plans
  const dayKeys = useMemo(
    () => [...new Map(combinedEvents.map((e) => [e.day, true])).keys()].sort(),
    [combinedEvents],
  );
  const [dayIdx, setDayIdx] = useState(0);
  useEffect(() => {
    if (dayIdx > dayKeys.length - 1) setDayIdx(Math.max(0, dayKeys.length - 1));
  }, [dayKeys.length, dayIdx]);
  const currentDay = dayKeys[dayIdx] || combinedEvents[0]?.day;
  const viewEvents = useMemo(
    () => combinedEvents.filter((e) => e.day === currentDay),
    [combinedEvents, currentDay],
  );
  const viewRemarks = useMemo(
    () => remarks.filter((r) => r.timestamp.slice(0, 10) === currentDay),
    [remarks, currentDay],
  );

  function parseISO(ts: string) {
    return new Date(ts).getTime();
  }

  function minutesBetween(a: string, b: string) {
    return Math.max(0, Math.round((parseISO(b) - parseISO(a)) / 60000));
  }

  function validateHosWith(
    entries: { timestamp: string; status: LogStatus }[],
    newEntry?: { timestamp: string; status: LogStatus },
  ): string | null {
    // Build a simple HOS state machine across entries (assumes midnight OFF seed)
    const seq = [...entries];
    if (newEntry) seq.push(newEntry);
    seq.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    if (!seq.length) return null;
    // roll-up driving minutes in current 14-hour window and 8-hour driving since last break
    let windowStart = seq[0].timestamp; // first on-duty/off-duty boundary of day
    let drivingSinceBreakMin = 0;
    let onDutyWindowMin = 0;
    let cumulativeDutyMin = 0; // counts ON_DUTY + DRIVING for totals
    let last = seq[0];
    for (let i = 1; i < seq.length; i++) {
      const cur = seq[i];
      const span = minutesBetween(last.timestamp, cur.timestamp);
      // accrue span to last.status
      if (last.status === "DRIVING") {
        drivingSinceBreakMin += span;
        cumulativeDutyMin += span;
      } else if (last.status === "ON_DUTY") {
        cumulativeDutyMin += span;
      }
      onDutyWindowMin = minutesBetween(windowStart, cur.timestamp);
      // Break reset conditions
      if (last.status !== "DRIVING" && span >= 30) {
        drivingSinceBreakMin = 0;
      }
      // Off-duty reset window if >=10h off (sleeper or off)
      if ((last.status === "OFF" || last.status === "SLEEPER") && span >= 10 * 60) {
        windowStart = cur.timestamp;
        onDutyWindowMin = 0;
        drivingSinceBreakMin = 0;
        cumulativeDutyMin = 0;
      }
      // Check constraints at the transition moment
      if (drivingSinceBreakMin > 8 * 60) return "Must take 30-min break after 8 hours driving";
      if (cumulativeDutyMin > 11 * 60) return "Exceeds 11-hour driving limit";
      if (onDutyWindowMin > 14 * 60) return "Exceeds 14-hour duty window";
      last = cur;
    }
    return null;
  }

  useEffect(() => {
    const el = graphWrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0]?.contentRect;
      if (!cr) return;
      const w = Math.max(640, Math.floor(cr.width));
      const h = Math.max(260, Math.floor(w / 4)); // keep ~4:1 aspect like paper log
      setGraphSize({ w, h });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        current_location: currentLocation,
        pickup_location: pickupLocation,
        dropoff_location: dropoffLocation,
        log_date: logDate,
        co_driver_name: coDriverName,
        tractor_number: tractorNumber,
        trailer_numbers: trailerNumbers,
        other_trailers: otherTrailers,
        shipper_name: shipperName,
        commodity_description: commodityDescription,
        load_id: loadId,
      };
      if (currentCycleUsedHrs) payload.current_cycle_used_hrs = Number(currentCycleUsedHrs);
      const created = await TripsAPI.create(payload);
      // fetch full detail to ensure route_metadata present
      const detail = await TripsAPI.detail(created.id);
      setTrip(detail);
      const logList = await LogsAPI.list(detail.id);
      setLogs(logList);
      try {
        // Best-effort refresh of dashboard stats
        await api("/api/drivers/dashboard/");
      } catch {}
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const pickupCoord = parseCoord(pickupLocation);
  const dropoffCoord = parseCoord(dropoffLocation);
  const currentCoord = parseCoord(currentLocation);

  async function autoGenerateDay() {
    if (!trip) return;
    const startDay = logs[0]?.day || new Date().toISOString().slice(0, 10);
    const fmt = (dayStr: string, minutes: number) => {
      const hh = String(Math.floor(minutes / 60) % 24).padStart(2, "0");
      const mm = String(minutes % 60).padStart(2, "0");
      return `${dayStr}T${hh}:${mm}:00Z`;
    };
    const nextDay = (dayStr: string) => {
      const d = new Date(`${dayStr}T00:00:00Z`);
      d.setUTCDate(d.getUTCDate() + 1);
      return d.toISOString().slice(0, 10);
    };
    let remainingDriveMin = Math.round(Number(trip.estimated_hours || 0) * 60);
    if (!Number.isFinite(remainingDriveMin) || remainingDriveMin <= 0) remainingDriveMin = 11 * 60;
    let dayStr = startDay;
    let t = 6 * 60; // start at 06:00
    const evs: LogEvent[] = [];
    const rms: { timestamp: string; city: string; state: string; activity: string }[] = [];
    const push = (status: LogStatus, note?: string) => {
      const ts = fmt(dayStr, t);
      evs.push({
        id: evs.length + 1,
        trip: trip!.id,
        driver: 0,
        day: dayStr,
        timestamp: ts,
        status,
        created_at: ts,
      });
      if (note) rms.push({ timestamp: ts, city: "", state: "", activity: note });
    };
    while (remainingDriveMin > 0) {
      // Start day with pre-trip
      push("ON_DUTY", "Pre-trip inspection");
      t += 60;
      let drivingToday = 0;
      let drivingSinceBreak = 0;
      const windowStart = t - 60;
      let fuelInserted = false;
      while (remainingDriveMin > 0 && drivingToday < 11 * 60 && t - windowStart < 14 * 60) {
        const block = Math.min(
          4 * 60,
          11 * 60 - drivingToday,
          remainingDriveMin,
          8 * 60 - drivingSinceBreak,
          14 * 60 - (t - windowStart),
        );
        if (block <= 0) break;
        push("DRIVING");
        t += block;
        drivingToday += block;
        drivingSinceBreak += block;
        remainingDriveMin -= block;
        if (!fuelInserted && drivingToday >= 7 * 60 && remainingDriveMin > 0) {
          push("ON_DUTY", "Fueling truck");
          t += 20;
          fuelInserted = true;
        }
        if (
          drivingSinceBreak >= 8 * 60 &&
          remainingDriveMin > 0 &&
          drivingToday < 11 * 60 &&
          t - windowStart < 14 * 60
        ) {
          push("OFF", "30-min break");
          t += 30;
          drivingSinceBreak = 0;
        }
      }
      // End-of-day wrap
      push("ON_DUTY", remainingDriveMin <= 0 ? "Drop-off" : "Post-trip");
      t += 15;
      push("SLEEPER", "Sleeper berth");
      t += 10 * 60;
      // advance to next day
      if (t >= 24 * 60) {
        dayStr = nextDay(dayStr);
        t = t % (24 * 60);
      } else {
        dayStr = nextDay(dayStr);
        t = 6 * 60;
      }
    }
    try {
      setSaving(true);
      for (const e of evs) {
        await LogsAPI.create(e.trip, e.status, e.timestamp);
      }
      const fresh = await LogsAPI.list(trip.id);
      setLogs(fresh);
      setRemarks(rms);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="py-6 grid gap-6">
      <h3 className="text-xl font-semibold">Trip Planner</h3>
      <form onSubmit={onSubmit} className="grid gap-3 max-w-2xl">
        <div className="grid md:grid-cols-3 gap-3">
          <input
            className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Current location (lon,lat)"
            value={currentLocation}
            onChange={(e) => setCurrentLocation(e.target.value)}
          />
          <input
            className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Pickup (lon,lat)"
            value={pickupLocation}
            onChange={(e) => setPickupLocation(e.target.value)}
          />
          <input
            className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Dropoff (lon,lat)"
            value={dropoffLocation}
            onChange={(e) => setDropoffLocation(e.target.value)}
          />
        </div>

        {/* Trip-specific header fields */}
        <div className="border border-gray-800 rounded-lg p-3 bg-gray-900 grid gap-3">
          <div className="grid md:grid-cols-3 gap-3">
            <label className="text-sm grid gap-1">
              <span>Log Date</span>
              <input
                type="date"
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700"
                value={logDate}
                onChange={(e) => setLogDate(e.target.value)}
              />
            </label>
            <label className="text-sm grid gap-1">
              <span>Co-driver Name</span>
              <input
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700"
                value={coDriverName}
                onChange={(e) => setCoDriverName(e.target.value)}
              />
            </label>
            <label className="text-sm grid gap-1">
              <span>Tractor Number</span>
              <input
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700"
                value={tractorNumber}
                onChange={(e) => setTractorNumber(e.target.value)}
              />
            </label>
          </div>
          <div className="grid md:grid-cols-3 gap-3">
            <label className="text-sm grid gap-1">
              <span>Trailer Number(s)</span>
              <input
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700"
                placeholder="comma-separated"
                value={trailerNumbers}
                onChange={(e) => setTrailerNumbers(e.target.value)}
              />
            </label>
            <label className="text-sm grid gap-1">
              <span>Other Trailers</span>
              <input
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700"
                value={otherTrailers}
                onChange={(e) => setOtherTrailers(e.target.value)}
              />
            </label>
            <label className="text-sm grid gap-1">
              <span>Shipper Name</span>
              <input
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700"
                value={shipperName}
                onChange={(e) => setShipperName(e.target.value)}
              />
            </label>
          </div>
          <div className="grid md:grid-cols-3 gap-3">
            <label className="text-sm grid gap-1">
              <span>Commodity Description</span>
              <input
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700"
                value={commodityDescription}
                onChange={(e) => setCommodityDescription(e.target.value)}
              />
            </label>
            <label className="text-sm grid gap-1">
              <span>Load ID</span>
              <input
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700"
                value={loadId}
                onChange={(e) => setLoadId(e.target.value)}
              />
            </label>
            <label className="text-sm grid gap-1">
              <span>Current cycle used hrs (optional)</span>
              <input
                className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700"
                value={currentCycleUsedHrs}
                onChange={(e) => setCurrentCycleUsedHrs(e.target.value)}
              />
            </label>
          </div>
        </div>

        <button
          type="submit"
          className="mt-1 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white w-max"
        >
          Plan Trip
        </button>
        {error && <div className="text-red-400 text-sm">{error}</div>}
      </form>

      {trip && (
        <div className="grid gap-4">
          <div className="text-sm text-gray-300">
            <span className="font-semibold">Distance:</span> {trip.distance_miles} miles
            {"  "}
            <span className="font-semibold ml-3">ETA:</span> {trip.estimated_hours} hrs
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <button
              className={`px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white font-semibold shadow ${
                manualOpen ? "ring-2 ring-blue-500" : ""
              }`}
              onClick={() => setManualOpen((v) => !v)}
            >
              Manual Input
            </button>
            <button
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold shadow disabled:opacity-50"
              onClick={() => autoGenerateDay()}
              disabled={saving || manualOpen}
              title={manualOpen ? "Close Manual Input to enable" : undefined}
            >
              {saving ? "Saving…" : "Automatic"}
            </button>
            <button
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold shadow disabled:opacity-50"
              onClick={async () => {
                if (!trip || !pending.length) return;
                try {
                  setSaving(true);
                  for (const p of pending) {
                    await LogsAPI.create(trip.id, p.status, p.timestamp);
                  }
                  const fresh = await LogsAPI.list(trip.id);
                  setLogs(fresh);
                  setPending([]);
                } catch (e) {
                  setError(e instanceof Error ? e.message : String(e));
                } finally {
                  setSaving(false);
                }
              }}
              disabled={saving || pending.length === 0}
            >
              Save
            </button>
          </div>
          {manualOpen && (
            <div className="rounded-xl bg-slate-800 p-3 border border-slate-700 flex gap-2 flex-wrap">
              {(["OFF", "SLEEPER", "DRIVING", "ON_DUTY"] as LogStatus[]).map((s) => (
                <button
                  key={s}
                  className={`px-3 py-1.5 rounded-lg font-semibold ${
                    s === "DRIVING"
                      ? "bg-blue-600 hover:bg-blue-500 text-white"
                      : "bg-slate-700 hover:bg-slate-600 text-gray-100"
                  }`}
                  onClick={() => {
                    const now = new Date();
                    const hh = String(now.getHours()).padStart(2, "0");
                    const mm = String(now.getMinutes()).padStart(2, "0");
                    setManualModal({
                      open: true,
                      status: s,
                      defaultActivity: s.replace("_", " "),
                      defaultTime: `${hh}:${mm}`,
                      defaultDate: (
                        combinedEvents[combinedEvents.length - 1]?.timestamp ||
                        new Date().toISOString()
                      ).slice(0, 10),
                    });
                  }}
                >
                  {s.replace("_", " ")}
                </button>
              ))}
            </div>
          )}
          <div
            ref={graphWrapRef}
            className="border border-gray-800 rounded-lg p-2 bg-gray-900 w-full"
          >
            {dayKeys.length > 1 && (
              <div className="flex items-center justify-between mb-2 text-sm text-gray-300">
                <button
                  className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50"
                  onClick={() => setDayIdx((i) => Math.max(0, i - 1))}
                  disabled={dayIdx === 0}
                >
                  ◀ Prev Day
                </button>
                <div>
                  Day {dayIdx + 1} / {dayKeys.length} — {currentDay}
                </div>
                <button
                  className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50"
                  onClick={() => setDayIdx((i) => Math.min(dayKeys.length - 1, i + 1))}
                  disabled={dayIdx >= dayKeys.length - 1}
                >
                  Next Day ▶
                </button>
              </div>
            )}
            <LogGraph
              events={viewEvents}
              remarks={viewRemarks}
              width={graphSize.w}
              height={graphSize.h}
              completeDay={true}
              seedMidnightOff={true}
              squareCells={true}
            />
          </div>
          <div className="grid gap-3 w-full items-start lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="w-full min-w-0">
              <MapDisplay
                route={trip.route_geometry}
                pickup={pickupCoord}
                dropoff={dropoffCoord}
                current={currentCoord}
                stops={trip.fueling_stops}
                metadata={trip.route_metadata}
              />
            </div>
            <DirectionsSidebar metadata={trip.route_metadata} />
          </div>
        </div>
      )}

      {remarkModal.open && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-slate-800 p-6 rounded-2xl shadow-lg">
            <div className="text-lg font-semibold mb-4">Add Remark</div>
            <RemarkForm
              defaultActivity={remarkModal.defaultActivity}
              onCancel={() => setRemarkModal({ open: false })}
              onSave={(city, state, activity) => {
                setRemarks((prev) => [
                  ...prev,
                  { timestamp: remarkModal.ts, city, state, activity },
                ]);
                setRemarkModal({ open: false });
              }}
            />
          </div>
        </div>
      )}

      {manualModal.open && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-slate-800 p-6 rounded-2xl shadow-lg">
            <div className="text-lg font-semibold mb-4">
              Add {manualModal.status.replace("_", " ")} Entry
            </div>
            <ManualEventForm
              defaultTime={manualModal.defaultTime}
              defaultActivity={manualModal.defaultActivity}
              defaultDate={manualModal.defaultDate as string}
              onCancel={() => setManualModal({ open: false })}
              onSave={(timeStr, city, state, activity, dateStr) => {
                const day =
                  dateStr ||
                  (
                    combinedEvents[combinedEvents.length - 1]?.timestamp || new Date().toISOString()
                  ).slice(0, 10);
                const ts = `${day}T${timeStr}:00Z`;
                const lastTs = combinedEvents[combinedEvents.length - 1]?.timestamp;
                if (lastTs && ts <= lastTs) {
                  setError("Time must be after the last entry");
                  return;
                }
                if (lastTs && lastTs.slice(0, 10) !== day) {
                  const gapMin = minutesBetween(lastTs, ts);
                  if (gapMin < 10 * 60) {
                    setError("Must have 10 consecutive hours off to start a new day");
                    return;
                  }
                }
                const hosErr = validateHosWith(
                  combinedEvents.map((e) => ({ timestamp: e.timestamp, status: e.status })),
                  { timestamp: ts, status: manualModal.status },
                );
                if (hosErr) {
                  setError(hosErr);
                  return;
                }
                setRemarks((prev) => [...prev, { timestamp: ts, city, state, activity }]);
                setPending((prev) => [...prev, { timestamp: ts, status: manualModal.status }]);
                setManualModal({ open: false });
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function RemarkForm({
  defaultActivity,
  onSave,
  onCancel,
}: {
  defaultActivity: string;
  onSave: (city: string, state: string, activity: string) => void;
  onCancel: () => void;
}) {
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [activity, setActivity] = useState(defaultActivity);
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(city, state, activity);
      }}
    >
      <div className="grid sm:grid-cols-3 gap-3">
        <input
          className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="City"
          value={city}
          onChange={(e) => setCity(e.target.value)}
        />
        <input
          className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="State"
          value={state}
          onChange={(e) => setState(e.target.value)}
        />
        <input
          className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="Activity (e.g., Fueling truck)"
          value={activity}
          onChange={(e) => setActivity(e.target.value)}
        />
      </div>
      <div className="flex gap-3 justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600"
        >
          Cancel
        </button>
        <button
          type="submit"
          className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold"
        >
          Save Remark
        </button>
      </div>
    </form>
  );
}

function ManualEventForm({
  defaultTime,
  defaultActivity,
  defaultDate,
  onSave,
  onCancel,
}: {
  defaultTime: string;
  defaultActivity: string;
  defaultDate: string;
  onSave: (time: string, city: string, state: string, activity: string, date?: string) => void;
  onCancel: () => void;
}) {
  const [time, setTime] = useState(defaultTime);
  const [date, setDate] = useState(defaultDate);
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [activity, setActivity] = useState(defaultActivity);
  return (
    <form
      className="grid gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(time, city, state, activity, date);
      }}
    >
      <div className="grid sm:grid-cols-5 gap-3">
        <input
          type="date"
          className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <input
          type="time"
          className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          value={time}
          onChange={(e) => setTime(e.target.value)}
        />
        <input
          className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="City"
          value={city}
          onChange={(e) => setCity(e.target.value)}
        />
        <input
          className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="State"
          value={state}
          onChange={(e) => setState(e.target.value)}
        />
        <input
          className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="Activity"
          value={activity}
          onChange={(e) => setActivity(e.target.value)}
        />
      </div>
      <div className="flex gap-3 justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600"
        >
          Cancel
        </button>
        <button
          type="submit"
          className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold"
        >
          Add
        </button>
      </div>
    </form>
  );
}
