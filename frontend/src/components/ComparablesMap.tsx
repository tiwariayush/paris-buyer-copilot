"use client";

import { useEffect, useMemo, useRef } from "react";
import maplibregl from "maplibre-gl";
import type { Comp, GeoLocation } from "@/lib/types";

const STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

export function ComparablesMap({
  comps,
  target,
}: {
  comps: Comp[];
  target?: GeoLocation | null;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const points = useMemo(
    () => comps.filter((c) => c.longitude != null && c.latitude != null),
    [comps],
  );

  const center = useMemo<[number, number]>(() => {
    if (target?.lon != null && target?.lat != null)
      return [target.lon, target.lat];
    if (points.length) return [points[0].longitude!, points[0].latitude!];
    return [2.3522, 48.8566]; // Paris fallback
  }, [target, points]);

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    mapRef.current = new maplibregl.Map({
      container: ref.current,
      style: STYLE,
      center,
      zoom: 14,
    });
    return () => {
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.flyTo({ center, zoom: 14 });

    // Clear old markers
    document.querySelectorAll(".pbc-marker").forEach((el) => el.remove());

    if (target) {
      const el = document.createElement("div");
      el.className = "pbc-marker pbc-target";
      el.style.cssText = `
        width: 18px; height: 18px; border-radius: 50%;
        background: var(--accent); border: 3px solid var(--card);
        box-shadow: 0 0 0 1px var(--accent), 0 4px 8px rgba(0,0,0,0.2);
      `;
      new maplibregl.Marker({ element: el })
        .setLngLat([target.lon, target.lat])
        .addTo(map);
    }

    points.forEach((c) => {
      const el = document.createElement("div");
      el.className = `pbc-marker pbc-${c.tier}`;
      const color =
        c.tier === "building"
          ? "#7c3aed"
          : c.tier === "street"
            ? "#2563eb"
            : "#9ca3af";
      el.style.cssText = `
        width: 12px; height: 12px; border-radius: 50%;
        background: ${color}; border: 2px solid white;
        box-shadow: 0 1px 2px rgba(0,0,0,0.25); cursor: pointer;
      `;
      const popup = new maplibregl.Popup({ offset: 12, closeButton: false }).setHTML(
        `<div style="font-family: var(--font-sans);font-size:12px;line-height:1.4">
          <div style="font-weight:600">${(c.adresse ?? "").replace(/</g, "&lt;")}</div>
          <div>${new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(c.valeur_fonciere)} · ${c.surface_reelle_bati ?? "?"} m²</div>
          <div style="color:#666">${c.date_mutation} · ${c.price_per_m2 ? Math.round(c.price_per_m2).toLocaleString("fr-FR") + " €/m²" : ""}</div>
        </div>`,
      );
      new maplibregl.Marker({ element: el })
        .setLngLat([c.longitude!, c.latitude!])
        .setPopup(popup)
        .addTo(map);
    });
  }, [center, points, target]);

  return (
    <div
      ref={ref}
      className="h-[420px] w-full rounded-2xl overflow-hidden border border-[var(--border)] bg-[var(--card)]"
    />
  );
}
