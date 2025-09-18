import { Fragment } from "react";

type RouteLegStep = {
  distance?: number;
  maneuver?: { instruction?: string };
};

type RouteMetadata = {
  distance?: number;
  duration?: number;
  legs?: { steps?: RouteLegStep[] }[];
} | null;

type Props = {
  metadata?: RouteMetadata;
};

function fmtMinutes(seconds?: number) {
  if (!seconds && seconds !== 0) return "—";
  const mins = Math.round(seconds / 60);
  return `${mins} min`;
}

function fmtMiles(meters?: number) {
  if (!meters && meters !== 0) return "—";
  const miles = meters / 1609.344;
  return `${miles.toFixed(1)} mi`;
}

export default function DirectionsSidebar({ metadata }: Props) {
  const route = (metadata || {}) as NonNullable<RouteMetadata> & Record<string, unknown>;
  const legs = Array.isArray(route.legs) ? route.legs : [];
  const steps: RouteLegStep[] = legs.flatMap((l) => (Array.isArray(l?.steps) ? l.steps! : []));

  return (
    <div className="rounded-2xl shadow-lg bg-slate-800 p-4 max-h-[400px] overflow-auto">
      <div className="mb-3 text-sm text-text-muted">
        <span className="font-semibold text-gray-200">Trip duration:</span>{" "}
        {fmtMinutes(route.duration)}
        <span className="mx-2">|</span>
        <span className="font-semibold text-gray-200">Distance:</span> {fmtMiles(route.distance)}
      </div>
      {steps.length ? (
        <ol className="list-decimal ml-5 space-y-1">
          {steps.map((s, idx: number) => (
            <li key={idx} className="text-gray-200">
              {s?.maneuver?.instruction || "Proceed"}
              {s?.distance ? (
                <Fragment>
                  {" "}
                  <span className="text-text-muted">({fmtMiles(s.distance)})</span>
                </Fragment>
              ) : null}
            </li>
          ))}
        </ol>
      ) : (
        <div className="text-text-muted">No turn-by-turn instructions available.</div>
      )}
    </div>
  );
}
