import { Card, CardLabel, CardTitle } from "./Card";
import { formatDate, formatEur } from "@/lib/api";
import type { Comp } from "@/lib/types";

export function BuildingHistory({ comps }: { comps: Comp[] }) {
  const buildingComps = comps
    .filter((c) => c.tier === "building")
    .slice()
    .sort(
      (a, b) =>
        new Date(b.date_mutation).getTime() -
        new Date(a.date_mutation).getTime(),
    );

  if (buildingComps.length === 0) {
    return (
      <Card>
        <CardLabel>Historique de l&apos;immeuble</CardLabel>
        <p className="text-sm text-[var(--muted)] mt-2">
          Aucune transaction publique trouvée pour cet immeuble dans les
          dernières années (DVF).
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <div>
          <CardLabel>Historique de l&apos;immeuble</CardLabel>
          <CardTitle className="mt-1">
            {buildingComps.length}{" "}
            {buildingComps.length === 1 ? "transaction" : "transactions"} dans
            le même bâtiment
          </CardTitle>
        </div>
      </div>
      <table className="w-full text-sm">
        <thead className="text-[var(--muted)] text-xs uppercase tracking-wider">
          <tr className="border-b border-[var(--border)]">
            <th className="text-left py-2 font-medium">Date</th>
            <th className="text-right py-2 font-medium">Prix</th>
            <th className="text-right py-2 font-medium">Surface</th>
            <th className="text-right py-2 font-medium">€/m²</th>
            <th className="text-right py-2 font-medium">Pièces</th>
          </tr>
        </thead>
        <tbody>
          {buildingComps.map((c) => (
            <tr key={c.id_mutation} className="border-b border-[var(--border)]/40">
              <td className="py-2">{formatDate(c.date_mutation)}</td>
              <td className="py-2 text-right font-mono">
                {formatEur(c.valeur_fonciere)}
              </td>
              <td className="py-2 text-right font-mono">
                {c.surface_reelle_bati ? `${c.surface_reelle_bati} m²` : "—"}
              </td>
              <td className="py-2 text-right font-mono">
                {c.price_per_m2
                  ? `${Math.round(c.price_per_m2).toLocaleString("fr-FR")} €`
                  : "—"}
              </td>
              <td className="py-2 text-right font-mono">
                {c.nombre_pieces_principales ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
