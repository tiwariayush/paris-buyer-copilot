"use client";

import { useMemo, useState } from "react";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  SlidersHorizontal,
  X,
} from "lucide-react";
import type { Comp, Listing } from "@/lib/types";
import { Card, CardLabel } from "@/components/Card";

type SortField =
  | "distance"
  | "price_similarity"
  | "surface_similarity"
  | "date"
  | "price_per_m2"
  | "price";
type SortDir = "asc" | "desc";

interface Filters {
  maxDistance: number | null;
  minSurface: number | null;
  maxSurface: number | null;
  minPrice: number | null;
  maxPrice: number | null;
  tiers: Set<string>;
}

const EMPTY_FILTERS: Filters = {
  maxDistance: null,
  minSurface: null,
  maxSurface: null,
  minPrice: null,
  maxPrice: null,
  tiers: new Set(["building", "street", "iris"]),
};

const SORT_OPTIONS: { value: SortField; label: string }[] = [
  { value: "distance", label: "Distance" },
  { value: "price_similarity", label: "Prix similaire" },
  { value: "surface_similarity", label: "Surface similaire" },
  { value: "date", label: "Date" },
  { value: "price_per_m2", label: "€/m²" },
  { value: "price", label: "Prix" },
];

function TierBadge({ tier }: { tier: string }) {
  const map: Record<string, { label: string; className: string }> = {
    building: {
      label: "Immeuble",
      className: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300",
    },
    street: {
      label: "Rue",
      className: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
    },
    iris: {
      label: "Quartier",
      className: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
    },
    none: {
      label: "—",
      className: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
    },
  };
  const v = map[tier] ?? map.none;
  return (
    <span
      className={`text-[10px] px-2 py-0.5 rounded-full font-medium whitespace-nowrap ${v.className}`}
    >
      {v.label}
    </span>
  );
}

function formatDistance(m: number | null | undefined): string {
  if (m == null) return "—";
  if (m < 1000) return `${Math.round(m)} m`;
  return `${(m / 1000).toFixed(1)} km`;
}

export function ComparablesTable({
  comps,
  listing,
  onHighlight,
}: {
  comps: Comp[];
  listing: Listing;
  onHighlight?: (comp: Comp | null) => void;
}) {
  const [sortField, setSortField] = useState<SortField>("distance");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [showFilters, setShowFilters] = useState(false);

  const listingPrice = listing.price_eur ?? 0;
  const listingSurface = listing.surface_m2 ?? 0;

  const filtered = useMemo(() => {
    return comps.filter((c) => {
      if (!filters.tiers.has(c.tier)) return false;
      if (filters.maxDistance != null && (c.distance_m ?? Infinity) > filters.maxDistance)
        return false;
      if (filters.minSurface != null && (c.surface_reelle_bati ?? 0) < filters.minSurface)
        return false;
      if (filters.maxSurface != null && (c.surface_reelle_bati ?? Infinity) > filters.maxSurface)
        return false;
      if (filters.minPrice != null && c.valeur_fonciere < filters.minPrice) return false;
      if (filters.maxPrice != null && c.valeur_fonciere > filters.maxPrice) return false;
      return true;
    });
  }, [comps, filters]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    const dir = sortDir === "asc" ? 1 : -1;

    arr.sort((a, b) => {
      let va: number;
      let vb: number;

      switch (sortField) {
        case "distance":
          va = a.distance_m ?? 99999;
          vb = b.distance_m ?? 99999;
          break;
        case "price_similarity":
          va = Math.abs((a.valeur_fonciere ?? 0) - listingPrice);
          vb = Math.abs((b.valeur_fonciere ?? 0) - listingPrice);
          break;
        case "surface_similarity":
          va = Math.abs((a.surface_reelle_bati ?? 0) - listingSurface);
          vb = Math.abs((b.surface_reelle_bati ?? 0) - listingSurface);
          break;
        case "date":
          va = new Date(a.date_mutation).getTime();
          vb = new Date(b.date_mutation).getTime();
          return dir * (vb - va); // most recent first by default
        case "price_per_m2":
          va = a.price_per_m2 ?? 0;
          vb = b.price_per_m2 ?? 0;
          break;
        case "price":
          va = a.valeur_fonciere;
          vb = b.valeur_fonciere;
          break;
        default:
          return 0;
      }
      return dir * (va - vb);
    });
    return arr;
  }, [filtered, sortField, sortDir, listingPrice, listingSurface]);

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.maxDistance != null) count++;
    if (filters.minSurface != null || filters.maxSurface != null) count++;
    if (filters.minPrice != null || filters.maxPrice != null) count++;
    if (filters.tiers.size < 3) count++;
    return count;
  }, [filters]);

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir(field === "date" ? "desc" : "asc");
    }
  }

  function resetFilters() {
    setFilters(EMPTY_FILTERS);
  }

  if (comps.length === 0) {
    return (
      <Card>
        <CardLabel>Comparables</CardLabel>
        <p className="text-sm text-[var(--muted)] mt-2">
          Aucun comparable trouvé. Le bien peut être atypique, ou la base DVF
          n&apos;est pas encore à jour pour cette adresse.
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <CardLabel>
          Ventes comparables ({sorted.length}/{comps.length})
        </CardLabel>
        <button
          onClick={() => setShowFilters((v) => !v)}
          className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
            showFilters || activeFilterCount > 0
              ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--accent-soft)]"
              : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--foreground)] hover:border-[var(--foreground)]/20"
          }`}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
          Filtres
          {activeFilterCount > 0 && (
            <span className="ml-1 bg-[var(--accent)] text-white text-[10px] rounded-full w-4 h-4 flex items-center justify-center">
              {activeFilterCount}
            </span>
          )}
        </button>
      </div>

      {showFilters && (
        <FilterPanel
          filters={filters}
          setFilters={setFilters}
          onReset={resetFilters}
          comps={comps}
        />
      )}

      {/* Sort pills */}
      <div className="mt-3 flex gap-1.5 flex-wrap">
        {SORT_OPTIONS.map((opt) => {
          const active = sortField === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => toggleSort(opt.value)}
              className={`flex items-center gap-1 text-[11px] font-medium px-2.5 py-1 rounded-full border transition-all ${
                active
                  ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "border-[var(--border)] text-[var(--muted)] hover:border-[var(--foreground)]/20 hover:text-[var(--foreground)]"
              }`}
            >
              {opt.label}
              {active &&
                (sortDir === "asc" ? (
                  <ArrowUp className="h-3 w-3" />
                ) : (
                  <ArrowDown className="h-3 w-3" />
                ))}
              {!active && <ArrowUpDown className="h-3 w-3 opacity-40" />}
            </button>
          );
        })}
      </div>

      {/* Table */}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[var(--muted)] text-xs uppercase tracking-wider">
            <tr className="border-b border-[var(--border)]">
              <th className="text-left py-2 font-medium">Tier</th>
              <th className="text-left py-2 font-medium">Adresse</th>
              <th className="text-left py-2 font-medium">Date</th>
              <th className="text-right py-2 font-medium">Prix</th>
              <th className="text-right py-2 font-medium">Surface</th>
              <th className="text-right py-2 font-medium">€/m²</th>
              <th className="text-right py-2 font-medium">Dist.</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((c) => (
              <tr
                key={c.id_mutation}
                className="border-b border-[var(--border)]/40 hover:bg-[var(--accent-soft)]/40 transition-colors cursor-pointer"
                onClick={() => onHighlight?.(c)}
                onMouseEnter={() => onHighlight?.(c)}
                onMouseLeave={() => onHighlight?.(null)}
              >
                <td className="py-2">
                  <TierBadge tier={c.tier} />
                </td>
                <td className="py-2 max-w-[200px] truncate">
                  {c.adresse ?? "—"}
                  {c.code_postal && (
                    <span className="text-[var(--muted)] text-xs ml-1">
                      {c.code_postal}
                    </span>
                  )}
                </td>
                <td className="py-2 font-mono text-xs">
                  {new Date(c.date_mutation).toLocaleDateString("fr-FR")}
                </td>
                <td className="py-2 text-right font-mono text-xs">
                  {new Intl.NumberFormat("fr-FR", {
                    style: "currency",
                    currency: "EUR",
                    maximumFractionDigits: 0,
                  }).format(c.valeur_fonciere)}
                </td>
                <td className="py-2 text-right font-mono text-xs">
                  {c.surface_reelle_bati ? `${c.surface_reelle_bati} m²` : "—"}
                </td>
                <td className="py-2 text-right font-mono text-xs">
                  {c.price_per_m2
                    ? `${Math.round(c.price_per_m2).toLocaleString("fr-FR")} €`
                    : "—"}
                </td>
                <td className="py-2 text-right font-mono text-xs text-[var(--muted)]">
                  {formatDistance(c.distance_m)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {sorted.length === 0 && filtered.length === 0 && (
        <div className="text-center py-6 text-sm text-[var(--muted)]">
          Aucun résultat avec ces filtres.{" "}
          <button
            onClick={resetFilters}
            className="text-[var(--accent)] hover:underline"
          >
            Réinitialiser
          </button>
        </div>
      )}
    </Card>
  );
}

function FilterPanel({
  filters,
  setFilters,
  onReset,
  comps,
}: {
  filters: Filters;
  setFilters: (f: Filters) => void;
  onReset: () => void;
  comps: Comp[];
}) {
  const maxDist = useMemo(() => {
    const dists = comps.map((c) => c.distance_m).filter((d): d is number => d != null);
    return dists.length ? Math.ceil(Math.max(...dists)) : 2000;
  }, [comps]);

  const surfaceRange = useMemo(() => {
    const surfaces = comps
      .map((c) => c.surface_reelle_bati)
      .filter((s): s is number => s != null);
    if (!surfaces.length) return [0, 200];
    return [Math.floor(Math.min(...surfaces)), Math.ceil(Math.max(...surfaces))];
  }, [comps]);

  const priceRange = useMemo(() => {
    const prices = comps.map((c) => c.valeur_fonciere);
    return [Math.floor(Math.min(...prices)), Math.ceil(Math.max(...prices))];
  }, [comps]);

  function toggleTier(tier: string) {
    const next = new Set(filters.tiers);
    if (next.has(tier)) next.delete(tier);
    else next.add(tier);
    if (next.size === 0) return;
    setFilters({ ...filters, tiers: next });
  }

  return (
    <div className="mt-3 p-4 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
          Filtres
        </span>
        <button
          onClick={onReset}
          className="text-[11px] text-[var(--accent)] hover:underline flex items-center gap-1"
        >
          <X className="h-3 w-3" />
          Réinitialiser
        </button>
      </div>

      {/* Tier filter */}
      <div>
        <label className="text-[11px] text-[var(--muted)] font-medium">Source</label>
        <div className="mt-1.5 flex gap-2">
          {(["building", "street", "iris"] as const).map((tier) => (
            <button
              key={tier}
              onClick={() => toggleTier(tier)}
              className={`text-[11px] px-2.5 py-1 rounded-full border transition-all ${
                filters.tiers.has(tier)
                  ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "border-[var(--border)] text-[var(--muted)] opacity-50"
              }`}
            >
              {tier === "building" ? "Immeuble" : tier === "street" ? "Rue" : "Quartier"}
            </button>
          ))}
        </div>
      </div>

      {/* Distance slider */}
      <div>
        <label className="text-[11px] text-[var(--muted)] font-medium">
          Distance max :{" "}
          <span className="text-[var(--foreground)]">
            {filters.maxDistance != null ? formatDistance(filters.maxDistance) : "Toutes"}
          </span>
        </label>
        <input
          type="range"
          min={0}
          max={maxDist}
          step={25}
          value={filters.maxDistance ?? maxDist}
          onChange={(e) => {
            const v = Number(e.target.value);
            setFilters({
              ...filters,
              maxDistance: v >= maxDist ? null : v,
            });
          }}
          className="w-full mt-1.5 accent-[var(--accent)]"
        />
      </div>

      {/* Surface range */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[11px] text-[var(--muted)] font-medium">
            Surface min (m²)
          </label>
          <input
            type="number"
            min={surfaceRange[0]}
            max={surfaceRange[1]}
            placeholder={String(surfaceRange[0])}
            value={filters.minSurface ?? ""}
            onChange={(e) =>
              setFilters({
                ...filters,
                minSurface: e.target.value ? Number(e.target.value) : null,
              })
            }
            className="mt-1 w-full px-2.5 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--card)] text-[var(--foreground)] focus:border-[var(--accent)] focus:outline-none transition-colors"
          />
        </div>
        <div>
          <label className="text-[11px] text-[var(--muted)] font-medium">
            Surface max (m²)
          </label>
          <input
            type="number"
            min={surfaceRange[0]}
            max={surfaceRange[1]}
            placeholder={String(surfaceRange[1])}
            value={filters.maxSurface ?? ""}
            onChange={(e) =>
              setFilters({
                ...filters,
                maxSurface: e.target.value ? Number(e.target.value) : null,
              })
            }
            className="mt-1 w-full px-2.5 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--card)] text-[var(--foreground)] focus:border-[var(--accent)] focus:outline-none transition-colors"
          />
        </div>
      </div>

      {/* Price range */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[11px] text-[var(--muted)] font-medium">
            Prix min (€)
          </label>
          <input
            type="number"
            min={priceRange[0]}
            max={priceRange[1]}
            step={10000}
            placeholder={String(priceRange[0])}
            value={filters.minPrice ?? ""}
            onChange={(e) =>
              setFilters({
                ...filters,
                minPrice: e.target.value ? Number(e.target.value) : null,
              })
            }
            className="mt-1 w-full px-2.5 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--card)] text-[var(--foreground)] focus:border-[var(--accent)] focus:outline-none transition-colors"
          />
        </div>
        <div>
          <label className="text-[11px] text-[var(--muted)] font-medium">
            Prix max (€)
          </label>
          <input
            type="number"
            min={priceRange[0]}
            max={priceRange[1]}
            step={10000}
            placeholder={String(priceRange[1])}
            value={filters.maxPrice ?? ""}
            onChange={(e) =>
              setFilters({
                ...filters,
                maxPrice: e.target.value ? Number(e.target.value) : null,
              })
            }
            className="mt-1 w-full px-2.5 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--card)] text-[var(--foreground)] focus:border-[var(--accent)] focus:outline-none transition-colors"
          />
        </div>
      </div>
    </div>
  );
}
