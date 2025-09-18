import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

type LineString = { type: "LineString"; coordinates: [number, number][] };

type Props = {
  route: LineString | null; // GeoJSON LineString
  pickup?: [number, number];
  dropoff?: [number, number];
  current?: [number, number];
  stops?: { mile?: number; coord?: [number, number] }[];
  metadata?: unknown;
};

// Use OpenStreetMap raster tiles as the basemap (no key required)
const osmStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [
    {
      id: "osm",
      type: "raster",
      source: "osm",
      minzoom: 0,
      maxzoom: 19,
    },
  ],
};

export default function MapDisplay({ route, pickup, dropoff, current, stops }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const center = pickup || dropoff || [-122.4, 37.8];
    const map = new maplibregl.Map({
      container: ref.current,
      style: osmStyle,
      center,
      zoom: 9,
    });

    let pickupMarker: maplibregl.Marker | undefined;
    let dropoffMarker: maplibregl.Marker | undefined;
    let currentMarker: maplibregl.Marker | undefined;
    const stopMarkers: maplibregl.Marker[] = [];

    if (pickup) {
      pickupMarker = new maplibregl.Marker({ color: "green" }).setLngLat(pickup).addTo(map);
    }
    if (dropoff) {
      dropoffMarker = new maplibregl.Marker({ color: "red" }).setLngLat(dropoff).addTo(map);
    }

    if (current) {
      currentMarker = new maplibregl.Marker({ color: "#ffd700" }).setLngLat(current).addTo(map);
    }

    if (route) {
      const feature = {
        type: "Feature",
        geometry: route,
        properties: {},
      } as GeoJSON.Feature<GeoJSON.LineString>;
      map.on("load", () => {
        // Ensure the map sizes correctly after being inserted in layout
        try {
          map.resize();
        } catch {
          // ignore
        }
        if (!map.getSource("route")) {
          map.addSource("route", { type: "geojson", data: feature });
          map.addLayer({
            id: "route-line",
            type: "line",
            source: "route",
            paint: { "line-color": "#1e90ff", "line-width": 4 },
          });
          try {
            const coords = route.coordinates || [];
            if (coords.length > 1) {
              const bounds = new maplibregl.LngLatBounds(coords[0], coords[0]);
              coords.forEach((c) => bounds.extend(c));
              map.fitBounds(bounds, { padding: 40 });
              try {
                map.resize();
              } catch {
                // ignore
              }
            }
          } catch {
            // ignore
          }
        }
      });
    }

    // Fueling/rest stops
    if (stops && stops.length) {
      stops.forEach((s) => {
        if (s.coord) {
          const m = new maplibregl.Marker({ color: "#ffa500" }).setLngLat(s.coord).addTo(map);
          stopMarkers.push(m);
        }
      });
    }

    const onWindowResize = () => {
      try {
        map.resize();
      } catch {
        // ignore
      }
    };
    window.addEventListener("resize", onWindowResize);

    return () => {
      pickupMarker?.remove();
      dropoffMarker?.remove();
      currentMarker?.remove();
      stopMarkers.forEach((m) => m.remove());
      window.removeEventListener("resize", onWindowResize);
      map.remove();
    };
  }, [route, pickup, dropoff, current, stops]);

  return (
    <div
      ref={ref}
      style={{ width: "100%", minWidth: 0, height: 420, borderRadius: 8, overflow: "hidden" }}
    />
  );
}
