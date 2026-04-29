import { Card, CardLabel, CardTitle } from "./Card";
import type { Neighborhood } from "@/lib/types";

export function NeighborhoodCard({ data }: { data?: Neighborhood | null }) {
  if (!data) return null;
  const schools = data.nearest_schools.slice(0, 5);
  return (
    <Card>
      <CardLabel>Quartier</CardLabel>
      <CardTitle className="mt-1">
        {data.iris_name ?? data.iris_code ?? "—"}
      </CardTitle>
      <div className="mt-4">
        <div className="text-xs uppercase tracking-wider text-[var(--muted)] mb-2">
          Écoles à proximité
        </div>
        {schools.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">Aucune école dans le rayon proche.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {schools.map((s, i) => (
              <li key={i} className="flex items-start justify-between gap-3">
                <span className="font-medium">{s.name ?? "—"}</span>
                <span className="text-xs text-[var(--muted)] flex-shrink-0">
                  {s.nature ?? s.type ?? ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
