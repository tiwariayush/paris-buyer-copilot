"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { analyze, formatEur } from "@/lib/api";
import type { AnalyzeResponse } from "@/lib/types";
import { PriceCard } from "@/components/PriceCard";
import { ComparablesMap } from "@/components/ComparablesMap";
import { BuildingHistory } from "@/components/BuildingHistory";
import { DPECard } from "@/components/DPECard";
import { NeighborhoodCard } from "@/components/NeighborhoodCard";
import { NegotiationScript } from "@/components/NegotiationScript";
import { Card, CardLabel, CardTitle } from "@/components/Card";

export default function VerdictView() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  // Legacy support: ?url=... still works for direct linking.
  const legacyUrl = params.get("url");
  const [data, setData] = useState<AnalyzeResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let content: string | null = null;
    let sourceUrl: string | undefined = undefined;
    if (id) {
      const raw = sessionStorage.getItem(`analyze:${id}`);
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as { content: string; source_url?: string | null };
          content = parsed.content;
          sourceUrl = parsed.source_url ?? undefined;
        } catch {
          /* ignore */
        }
      }
    } else if (legacyUrl) {
      content = legacyUrl;
    }

    if (!content) {
      setErr("Aucune annonce. Retournez à l'accueil et réessayez.");
      return;
    }

    setLoading(true);
    setErr(null);
    analyze(content, sourceUrl)
      .then(setData)
      .catch((e: Error) => setErr(e.message))
      .finally(() => setLoading(false));
  }, [id, legacyUrl]);

  if (!id && !legacyUrl) {
    return (
      <div className="flex-1 flex items-center justify-center text-[var(--muted)]">
        Aucune annonce.
      </div>
    );
  }

  return (
    <div className="flex-1 px-4 md:px-8 py-8 max-w-6xl mx-auto w-full">
      <button
        onClick={() => router.push("/")}
        className="flex items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)] mb-6 transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Nouvelle analyse
      </button>

      {loading && <LoadingState />}
      {err && (
        <Card>
          <CardLabel>Erreur</CardLabel>
          <CardTitle className="mt-1 text-[var(--negative)]">
            Analyse impossible
          </CardTitle>
          <p className="mt-2 text-sm text-[var(--muted)] break-words">{err}</p>
          <p className="mt-4 text-xs text-[var(--muted)]">
            Astuce : vérifiez que l&apos;annonce est publique et que l&apos;URL est complète.
          </p>
        </Card>
      )}

      {data && <Results data={data} />}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-4">
      <Card>
        <CardLabel>Analyse en cours</CardLabel>
        <CardTitle className="mt-1">Lecture de l&apos;annonce…</CardTitle>
        <ul className="mt-4 space-y-1.5 text-sm text-[var(--muted)] font-mono">
          <li>· Extraction des données structurées</li>
          <li>· Géocodage de l&apos;adresse</li>
          <li>· Recherche des comparables (DVF)</li>
          <li>· Lookup DPE</li>
          <li>· Génération du verdict</li>
        </ul>
      </Card>
    </div>
  );
}

function Results({ data }: { data: AnalyzeResponse }) {
  const { listing, valuation, comps, dpe, neighborhood, negotiation, location, delta_pct, delta_eur, warnings } =
    data;

  return (
    <div className="space-y-6">
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

      {warnings.length > 0 && (
        <div className="rounded-lg border border-[var(--warning)]/40 bg-amber-50/60 dark:bg-amber-900/10 px-4 py-2 text-xs text-[var(--warning)]">
          {warnings.map((w, i) => (
            <div key={i}>· {w}</div>
          ))}
        </div>
      )}

      <PriceCard
        listing={listing}
        valuation={valuation}
        comps={comps}
        deltaPct={delta_pct}
        deltaEur={delta_eur}
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <ComparablesMap comps={comps} target={location} />
        </div>
        <div className="space-y-6">
          <DPECard listing={listing} dpe={dpe} />
          <NeighborhoodCard data={neighborhood} />
        </div>
      </div>

      <BuildingHistory comps={comps} />

      {negotiation && <NegotiationScript script={negotiation} />}

      <CompsTable comps={comps} />

      {valuation.fair_value_eur && listing.price_eur ? (
        <div className="text-xs text-[var(--muted)] text-center pt-4">
          Sources : {valuation.n_comps} transactions DVF · estimation à{" "}
          {formatEur(valuation.fair_value_eur)}.
        </div>
      ) : null}
    </div>
  );
}

function CompsTable({ comps }: { comps: AnalyzeResponse["comps"] }) {
  const sorted = comps.slice().sort((a, b) => {
    const order = { building: 0, street: 1, iris: 2, none: 3 } as const;
    const ta = order[a.tier as keyof typeof order];
    const tb = order[b.tier as keyof typeof order];
    if (ta !== tb) return ta - tb;
    return new Date(b.date_mutation).getTime() - new Date(a.date_mutation).getTime();
  });

  if (sorted.length === 0) {
    return (
      <Card>
        <CardLabel>Comparables</CardLabel>
        <p className="text-sm text-[var(--muted)] mt-2">
          Aucun comparable trouvé. Le bien peut être atypique, ou la base
          DVF n&apos;est pas encore à jour pour cette adresse.
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <CardLabel>Toutes les ventes comparables ({sorted.length})</CardLabel>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-[var(--muted)] text-xs uppercase tracking-wider">
            <tr className="border-b border-[var(--border)]">
              <th className="text-left py-2 font-medium">Tier</th>
              <th className="text-left py-2 font-medium">Adresse</th>
              <th className="text-left py-2 font-medium">Date</th>
              <th className="text-right py-2 font-medium">Prix</th>
              <th className="text-right py-2 font-medium">Surface</th>
              <th className="text-right py-2 font-medium">€/m²</th>
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 30).map((c) => (
              <tr key={c.id_mutation} className="border-b border-[var(--border)]/40">
                <td className="py-2">
                  <TierBadge tier={c.tier} />
                </td>
                <td className="py-2">
                  {c.adresse ?? "—"}
                  {c.code_postal ? (
                    <span className="text-[var(--muted)] text-xs ml-1">
                      {c.code_postal}
                    </span>
                  ) : null}
                </td>
                <td className="py-2 font-mono">
                  {new Date(c.date_mutation).toLocaleDateString("fr-FR")}
                </td>
                <td className="py-2 text-right font-mono">
                  {new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(c.valeur_fonciere)}
                </td>
                <td className="py-2 text-right font-mono">
                  {c.surface_reelle_bati ? `${c.surface_reelle_bati} m²` : "—"}
                </td>
                <td className="py-2 text-right font-mono">
                  {c.price_per_m2
                    ? `${Math.round(c.price_per_m2).toLocaleString("fr-FR")} €`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function TierBadge({ tier }: { tier: string }) {
  const map: Record<string, { label: string; className: string }> = {
    building: { label: "Immeuble", className: "bg-purple-100 text-purple-800" },
    street: { label: "Rue", className: "bg-blue-100 text-blue-800" },
    iris: { label: "Quartier", className: "bg-gray-100 text-gray-700" },
    none: { label: "—", className: "bg-gray-100 text-gray-500" },
  };
  const v = map[tier] ?? map.none;
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${v.className}`}>
      {v.label}
    </span>
  );
}
