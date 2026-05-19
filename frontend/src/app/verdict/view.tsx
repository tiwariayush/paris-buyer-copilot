"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { analyzeStream, formatEur } from "@/lib/api";
import type { AnalyzeResponse, Listing } from "@/lib/types";
import { PriceCard } from "@/components/PriceCard";
import { ComparablesMap } from "@/components/ComparablesMap";
import { BuildingHistory } from "@/components/BuildingHistory";
import { DPECard } from "@/components/DPECard";
import { NeighborhoodCard } from "@/components/NeighborhoodCard";
import { NegotiationScript } from "@/components/NegotiationScript";
import { ComparablesTable } from "@/components/ComparablesTable";
import { ListingPreview } from "@/components/ListingPreview";
import { PremiumFeaturesCard } from "@/components/PremiumFeaturesCard";
import { Card, CardLabel, CardTitle } from "@/components/Card";

export default function VerdictView() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const legacyUrl = params.get("url");
  const [listing, setListing] = useState<Listing | null>(null);
  const [data, setData] = useState<AnalyzeResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

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
    setListing(null);
    setData(null);

    const abort = new AbortController();
    abortRef.current = abort;

    analyzeStream(
      content,
      sourceUrl,
      {
        onListing: (l) => setListing(l),
        onVerdict: (d) => {
          setData(d);
          setLoading(false);
        },
        onError: (detail) => {
          setErr(detail);
          setLoading(false);
        },
      },
      abort.signal,
    ).catch((e: Error) => {
      if (e.name !== "AbortError") {
        setErr(e.message);
        setLoading(false);
      }
    });

    return () => abort.abort();
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

      {loading && !listing && <LoadingState />}
      {loading && listing && <ListingPreview listing={listing} />}
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
  const {
    listing,
    valuation,
    comps,
    dpe,
    neighborhood,
    negotiation,
    location,
    delta_pct,
    delta_eur,
    warnings,
    premium_features,
    market_index,
  } = data;

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
          {premium_features && (
            <PremiumFeaturesCard
              premium={premium_features}
              adjustments={valuation.adjustments}
            />
          )}
          <DPECard listing={listing} dpe={dpe} />
          <NeighborhoodCard data={neighborhood} marketIndex={market_index} />
        </div>
      </div>

      <BuildingHistory comps={comps} />

      {negotiation && <NegotiationScript script={negotiation} />}

      <ComparablesTable comps={comps} listing={listing} />

      {valuation.fair_value_eur && listing.price_eur ? (
        <div className="text-xs text-[var(--muted)] text-center pt-4">
          Sources : {valuation.n_comps} transactions DVF · estimation à{" "}
          {formatEur(valuation.fair_value_eur)}.
        </div>
      ) : null}
    </div>
  );
}

