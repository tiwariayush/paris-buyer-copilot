import { Card, CardLabel, CardTitle } from "./Card";
import type { DPEReport, Listing } from "@/lib/types";
import { cn } from "@/lib/cn";

const colors: Record<string, string> = {
  A: "bg-emerald-600",
  B: "bg-emerald-500",
  C: "bg-lime-500",
  D: "bg-yellow-500",
  E: "bg-orange-500",
  F: "bg-red-500",
  G: "bg-red-700",
};

export function DPECard({
  listing,
  dpe,
}: {
  listing: Listing;
  dpe?: DPEReport | null;
}) {
  const cls = (dpe?.dpe_class ?? listing.dpe_class ?? "").toUpperCase();
  if (!cls) {
    return (
      <Card>
        <CardLabel>DPE</CardLabel>
        <p className="text-sm text-[var(--muted)] mt-2">
          Aucun DPE trouvé pour cette adresse.
        </p>
      </Card>
    );
  }
  const passoire = cls === "F" || cls === "G";

  return (
    <Card>
      <div className="flex items-start gap-4">
        <div
          className={cn(
            "h-16 w-16 rounded-xl flex items-center justify-center text-3xl font-bold text-white",
            colors[cls] ?? "bg-gray-400",
          )}
        >
          {cls}
        </div>
        <div className="flex-1">
          <CardLabel>Performance énergétique</CardLabel>
          <CardTitle className="mt-1">
            {passoire
              ? `Passoire thermique (${cls})`
              : `Classe ${cls}`}
          </CardTitle>
          {dpe?.consumption_kwh_m2_year ? (
            <div className="text-sm text-[var(--muted)] font-mono mt-1">
              {Math.round(dpe.consumption_kwh_m2_year)} kWh/m²·an
              {dpe.emissions_kgco2_m2_year
                ? ` · ${Math.round(dpe.emissions_kgco2_m2_year)} kgCO₂/m²·an`
                : null}
            </div>
          ) : null}
          {passoire ? (
            <p className="text-xs text-[var(--negative)] mt-2">
              Travaux énergétiques obligatoires : interdiction de louer dès
              {cls === "G" ? " 2025" : " 2028"}. Levier de négociation fort.
            </p>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
