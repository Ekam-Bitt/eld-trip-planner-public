import { useMemo, useCallback } from "react";
import type { LogEvent, LogStatus } from "../api";

type Props = {
  events: LogEvent[];
  remarks?: { timestamp: string; city: string; state: string; activity: string }[];
  width?: number;
  height?: number;
  completeDay?: boolean; // extend the last segment to 24:00 (default true)
  seedMidnightOff?: boolean; // ensure graph starts at 00:00 OFF (default true)
  squareCells?: boolean; // make 1h x row cells square by adjusting grid height
};

// Map statuses to y-levels (0=OFF,1=SB,2=DR,3=ON)
const LEVEL: Record<LogStatus, number> = {
  OFF: 0,
  SLEEPER: 1,
  DRIVING: 2,
  ON_DUTY: 3,
};

function clamp01(n: number) {
  return Math.max(0, Math.min(1, n));
}

export default function LogGraph({
  events,
  remarks = [],
  width = 1280,
  height = 360,
  completeDay = true,
  seedMidnightOff = true,
  squareCells = false,
}: Props) {
  const padding = 72;
  const remarksSpace = 48; // reserved space below the grid for remark labels
  const innerW = width - padding * 2;
  // If square cells requested, compute grid height from width so (innerW/24) == (gridH/4)
  const desiredGridH = squareCells ? innerW / 6 : undefined; // innerW/24 * 4
  const computedSvgH = squareCells ? padding * 2 + (desiredGridH ?? 0) + remarksSpace : height;
  const innerH = computedSvgH - padding * 2;
  const gridTop = padding;
  const gridBottom = padding + innerH - remarksSpace;
  const gridH = Math.max(1, gridBottom - gridTop);

  const X = useCallback(
    (v: number) => {
      return padding + v * innerW;
    },
    [innerW],
  );
  const Y = useCallback(
    (level: number) => {
      // 6 horizontal boundaries (0..5) creating 5 equal rows; 0 is top
      const rows = 5;
      return gridTop + (gridH * level) / rows;
    },
    [gridTop, gridH],
  );

  const { pathD, totals } = useMemo(() => {
    // Build segments across a 24h window of the day from events[0]?.day
    if (!events.length)
      return { pathD: "", totals: { OFF: 24, SLEEPER: 0, DRIVING: 0, ON_DUTY: 0 } };
    const day = events[0].day; // YYYY-MM-DD
    const start = new Date(`${day}T00:00:00Z`).getTime();
    const end = new Date(`${day}T24:00:00Z`).getTime();
    const sorted = [...events].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    const entries = sorted.map((e) => ({
      t: new Date(e.timestamp).getTime(),
      y: LEVEL[e.status],
      s: e.status,
    }));
    // Seed 00:00 OFF if requested and first event not at midnight
    if (seedMidnightOff && (!entries.length || entries[0].t > start)) {
      entries.unshift({ t: start, y: LEVEL.OFF, s: "OFF" });
    }
    let hasStub = false;
    if (completeDay) {
      entries.push({ t: end, y: entries[entries.length - 1].y, s: entries[entries.length - 1].s });
    } else {
      // Add a tiny horizontal stub so the graph doesn't end on a vertical line only
      const last = entries[entries.length - 1];
      const stubT = Math.min(end, last.t + 60 * 1000); // +1 minute
      if (stubT > last.t) {
        entries.push({ t: stubT, y: last.y, s: last.s });
        hasStub = true;
      }
    }

    const toX = (t: number) => X(clamp01((t - start) / (end - start)));
    const rowCenter = (row: number) => (Y(row) + Y(row + 1)) / 2;

    let d = `M ${toX(entries[0].t)} ${rowCenter(entries[0].y)}`;
    const totalsMin = { OFF: 0, SLEEPER: 0, DRIVING: 0, ON_DUTY: 0 } as Record<LogStatus, number>;
    for (let i = 0; i < entries.length - 1; i++) {
      const a = entries[i];
      const b = entries[i + 1];
      const xb = toX(b.t);
      d += ` L ${xb} ${rowCenter(a.y)}`; // horizontal to next timestamp
      if (b.y !== a.y) {
        d += ` L ${xb} ${rowCenter(b.y)}`; // vertical change
      }
      const minutes = Math.max(0, Math.round((b.t - a.t) / 60000));
      // Do not count the artificial stub minute in totals
      const isFinalStubPair = hasStub && i === entries.length - 2;
      if (!isFinalStubPair) {
        totalsMin[a.s as LogStatus] += minutes;
      }
    }
    const totals = {
      OFF: Math.round((totalsMin.OFF / 60) * 100) / 100,
      SLEEPER: Math.round((totalsMin.SLEEPER / 60) * 100) / 100,
      DRIVING: Math.round((totalsMin.DRIVING / 60) * 100) / 100,
      ON_DUTY: Math.round((totalsMin.ON_DUTY / 60) * 100) / 100,
    };
    return { pathD: d, totals };
  }, [events, X, Y, completeDay, seedMidnightOff]);

  // ELD-style grid colors
  const majorGridStyle = { stroke: "#4a69bd", strokeWidth: 1.5 };
  const borderStyle = { stroke: "#4a69bd", strokeWidth: 1.5, fill: "#fff" };
  const driverLineStyle = { stroke: "#111", strokeWidth: 4 };
  const headerStyle = { fill: "#111" } as const;
  const headerTextFill = "#fff";

  return (
    <svg width={width} height={computedSvgH} role="img" aria-label="HOS 24h log graph">
      {/* Top header bar with hour labels */}
      {(() => {
        const headerHeight = 40;
        const headerY = padding - headerHeight;
        const textY = headerY + headerHeight / 2 + 3;
        return (
          <g>
            <rect
              x={padding}
              y={headerY}
              width={innerW}
              height={headerHeight}
              style={headerStyle}
            />
            {Array.from({ length: 24 }, (_, h) => h).map((h) => {
              const isSpecial = h === 0 || h === 12;
              const label = h === 0 ? "Midnight" : h === 12 ? "Noon" : String(h % 12);
              const x = X(h / 24) + (h === 0 ? 4 : 0);
              return (
                <text
                  key={`hdr-${h}`}
                  x={x}
                  y={textY}
                  textAnchor={isSpecial ? "middle" : "middle"}
                  fontSize={11}
                  fill={headerTextFill}
                  dominantBaseline="middle"
                  transform={isSpecial ? `rotate(-90, ${x}, ${textY})` : undefined}
                >
                  {label}
                </text>
              );
            })}
            <text
              x={X(1)}
              y={textY}
              textAnchor="middle"
              fontSize={11}
              fill={headerTextFill}
              dominantBaseline="middle"
              transform={`rotate(-90, ${X(1) - 4}, ${textY})`}
            >
              Midnight
            </text>
          </g>
        );
      })()}
      {/* Grid area background/border */}
      <rect x={padding} y={gridTop} width={innerW} height={gridH} style={borderStyle} />

      {/* Vertical grid lines: only hours across full height */}
      {Array.from({ length: 24 + 1 }, (_, h) => h).map((h) => (
        <line
          key={`grid-hour-${h}`}
          x1={X(h / 24)}
          y1={gridTop}
          x2={X(h / 24)}
          y2={gridBottom}
          style={majorGridStyle}
        />
      ))}

      {/* Horizontal grid lines: 5 lines creating 4 rows */}
      {Array.from({ length: 5 }, (_, i) => (
        <line
          key={`row-boundary-${i}`}
          x1={X(0)}
          y1={Y(i)}
          x2={X(1)}
          y2={Y(i)}
          style={majorGridStyle}
        />
      ))}

      {/* Intra-hour ticks: rows 0-1 base at lines 1/2 (down), rows 2-3 base at 4/5 (up) */}
      {Array.from({ length: 4 }, (_, row) => row).map((row) => {
        // Row boundaries are at Y(row) and Y(row + 1)
        const yTop = Y(row);
        const yBottom = Y(row + 1);
        const rowHeight = yBottom - yTop;
        const isTopRows = row < 2;
        const baseY = isTopRows ? (row === 0 ? Y(0) : Y(1)) : row === 2 ? Y(3) : Y(4);
        return (
          <g key={`row-ticks-${row}`}>
            {Array.from({ length: 24 }, (_, h) => h).map((h) =>
              [0.25, 0.5, 0.75].map((q, idx) => {
                const x = X((h + q) / 24);
                const len = q === 0.5 ? rowHeight * 0.5 : rowHeight * 0.25;
                const y1 = baseY;
                const y2 = isTopRows ? baseY + len : baseY - len;
                return (
                  <line
                    key={`row-${row}-h-${h}-q-${idx}`}
                    x1={x}
                    y1={y1}
                    x2={x}
                    y2={y2}
                    style={majorGridStyle}
                  />
                );
              }),
            )}
          </g>
        );
      })}

      {/* Official left labels with row numbers - vertically centered in each row */}
      <g fontSize={12} fill="#2b4a9b" fontWeight={600}>
        <text x={padding - 10} y={(Y(0) + Y(1)) / 2} textAnchor="end" dominantBaseline="middle">
          1: OFF DUTY
        </text>
        <text x={padding - 10} y={(Y(1) + Y(2)) / 2 - 6} textAnchor="end" dominantBaseline="middle">
          2: SLEEPER
          <tspan x={padding - 10} dy={12}>
            BERTH
          </tspan>
        </text>
        <text x={padding - 10} y={(Y(2) + Y(3)) / 2} textAnchor="end" dominantBaseline="middle">
          3: DRIVING
        </text>
        <text x={padding - 10} y={(Y(3) + Y(4)) / 2 - 6} textAnchor="end" dominantBaseline="middle">
          4: ON DUTY
          <tspan x={padding - 10} dy={12} fontSize={11}>
            (NOT DRIVING)
          </tspan>
        </text>
        {/* Remarks label removed; remarks now rendered outside the grid */}
      </g>

      {/* Top ticks and labels shown via header bar above */}

      {/* Bottom scale removed */}

      {/* Driver path */}
      {pathD && (
        <path
          d={pathD}
          stroke={driverLineStyle.stroke}
          strokeWidth={driverLineStyle.strokeWidth}
          fill="none"
        />
      )}

      {/* Running totals on the right */}
      {(() => {
        const rightX = X(1) + 12;
        const line = (label: string, val: number, row: number) => (
          <text
            key={label}
            x={rightX}
            y={(Y(row) + Y(row + 1)) / 2}
            fontSize={12}
            fill="#2b4a9b"
            dominantBaseline="middle"
          >
            {label}: {val.toFixed(2)}h
          </text>
        );
        return (
          <g>
            {line("OFF", totals.OFF ?? 0, 0)}
            {line("SB", totals.SLEEPER ?? 0, 1)}
            {line("DR", totals.DRIVING ?? 0, 2)}
            {line("ON", totals.ON_DUTY ?? 0, 3)}
          </g>
        );
      })()}

      {/* Remarks markers: vertical line dropping from remarks row, with vertical text on sides */}
      {(() => {
        if (!remarks?.length) return null;
        const day = events[0]?.day || new Date().toISOString().slice(0, 10);
        const start = new Date(`${day}T00:00:00Z`).getTime();
        const end = new Date(`${day}T24:00:00Z`).getTime();
        const toX = (t: number) => X(clamp01((t - start) / (end - start)));
        const bottomGridY = Y(4);
        const lineLen = 12;
        const pivotY = Math.min(bottomGridY + lineLen + 14, height - 6);
        return (
          <g>
            {remarks.map((r, idx) => {
              const t = new Date(r.timestamp).getTime();
              const x = toX(t);
              const labelLeft = `${r.city}, ${r.state}`.trim();
              const labelRight = r.activity;
              return (
                <g key={`remark-${idx}`}>
                  <line
                    x1={x}
                    y1={bottomGridY}
                    x2={x}
                    y2={bottomGridY + lineLen}
                    stroke="#111"
                    strokeWidth={2}
                  />
                  {/* Left vertical text */}
                  <text
                    x={x - 6}
                    y={pivotY}
                    fontSize={11}
                    fill="#111"
                    textAnchor="end"
                    alignmentBaseline="middle"
                    transform={`rotate(-90, ${x - 6}, ${pivotY})`}
                  >
                    {labelLeft}
                  </text>
                  {/* Right vertical text */}
                  <text
                    x={x + 6}
                    y={pivotY}
                    fontSize={11}
                    fill="#111"
                    textAnchor="start"
                    alignmentBaseline="middle"
                    transform={`rotate(-90, ${x + 6}, ${pivotY})`}
                  >
                    {labelRight}
                  </text>
                </g>
              );
            })}
          </g>
        );
      })()}
    </svg>
  );
}
