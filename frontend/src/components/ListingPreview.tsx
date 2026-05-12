import { Card, CardLabel } from "./Card";
import type { Listing } from "@/lib/types";
import { formatEur } from "@/lib/api";
import {
  MapPin,
  Ruler,
  DoorOpen,
  BedDouble,
  Building2,
  ArrowUpDown,
  Zap,
} from "lucide-react";

const DPE_COLORS: Record<string, string> = {
  A: "bg-emerald-600",
  B: "bg-emerald-500",
  C: "bg-lime-500",
  D: "bg-yellow-500",
  E: "bg-orange-500",
  F: "bg-red-500",
  G: "bg-red-700",
};

export function ListingPreview({ listing }: { listing: Listing }) {
  const dpe = listing.dpe_class?.toUpperCase();

  return (
    <div className="space-y-4 animate-in fade-in duration-500">
      <header>
        <div className="text-xs uppercase tracking-[0.2em] text-[var(--accent)] font-semibold">
          {listing.portal}
          {listing.address_raw ? (
            <span className="text-[var(--muted)] font-normal normal-case tracking-normal ml-2">
              · {listing.address_raw}
            </span>
          ) : null}
        </div>
        <h1 className="mt-2 text-2xl md:text-3xl font-semibold tracking-tight">
          {listing.title ?? "Annonce"}
        </h1>
      </header>

      {listing.photos.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1 snap-x">
          {listing.photos.slice(0, 6).map((url, i) => (
            <img
              key={i}
              src={url}
              alt={`Photo ${i + 1}`}
              className="h-40 md:h-52 rounded-xl object-cover snap-start shrink-0"
              loading={i > 2 ? "lazy" : "eager"}
            />
          ))}
        </div>
      )}

      <Card>
        <CardLabel>Caractéristiques du bien</CardLabel>
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 gap-4">
          {listing.price_eur != null && (
            <Stat
              icon={<Building2 className="h-4 w-4" />}
              label="Prix affiché"
              value={formatEur(listing.price_eur)}
            />
          )}
          {listing.surface_m2 != null && (
            <Stat
              icon={<Ruler className="h-4 w-4" />}
              label="Surface"
              value={`${listing.surface_m2} m²`}
            />
          )}
          {listing.price_eur != null && listing.surface_m2 != null && listing.surface_m2 > 0 && (
            <Stat
              icon={<Zap className="h-4 w-4" />}
              label="Prix / m²"
              value={formatEur(listing.price_eur / listing.surface_m2)}
            />
          )}
          {listing.rooms != null && (
            <Stat
              icon={<DoorOpen className="h-4 w-4" />}
              label="Pièces"
              value={`${listing.rooms}`}
            />
          )}
          {listing.bedrooms != null && (
            <Stat
              icon={<BedDouble className="h-4 w-4" />}
              label="Chambres"
              value={`${listing.bedrooms}`}
            />
          )}
          {listing.floor != null && (
            <Stat
              icon={<ArrowUpDown className="h-4 w-4" />}
              label="Étage"
              value={
                listing.has_elevator
                  ? `${listing.floor}e · ascenseur`
                  : `${listing.floor}e${listing.has_elevator === false ? " · sans ascenseur" : ""}`
              }
            />
          )}
          {listing.address_raw && (
            <Stat
              icon={<MapPin className="h-4 w-4" />}
              label="Adresse"
              value={`${listing.address_raw}${listing.postal_code ? ` ${listing.postal_code}` : ""}`}
              wide
            />
          )}
          {dpe && (
            <div className="flex items-center gap-3">
              <div
                className={`h-9 w-9 rounded-lg flex items-center justify-center text-sm font-bold text-white ${DPE_COLORS[dpe] ?? "bg-gray-400"}`}
              >
                {dpe}
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-[var(--muted)]">
                  DPE
                </div>
                <div className="text-sm font-medium">Classe {dpe}</div>
              </div>
            </div>
          )}
        </div>
      </Card>

      <Card className="border-[var(--accent)]/30">
        <div className="flex items-center gap-3">
          <div className="relative flex h-5 w-5 items-center justify-center">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent)] opacity-30" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[var(--accent)]" />
          </div>
          <div>
            <p className="text-sm font-medium">
              Analyse en cours…
            </p>
            <p className="text-xs text-[var(--muted)]">
              Recherche des comparables, estimation de la valeur, génération du verdict
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
  wide,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  wide?: boolean;
}) {
  return (
    <div className={`flex items-start gap-2.5 ${wide ? "col-span-2 sm:col-span-3" : ""}`}>
      <div className="mt-0.5 text-[var(--accent)]">{icon}</div>
      <div>
        <div className="text-[10px] uppercase tracking-wider text-[var(--muted)]">
          {label}
        </div>
        <div className="text-sm font-medium">{value}</div>
      </div>
    </div>
  );
}
