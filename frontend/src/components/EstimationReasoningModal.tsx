"use client";

import { useMemo, useState } from "react";
import { CircleX, Download, Info, Printer } from "lucide-react";
import { formatDate, formatEur, formatPct } from "@/lib/api";
import type { Comp, Listing, Valuation } from "@/lib/types";

export function EstimationReasoningModal({
  listing,
  valuation,
  comps,
  deltaPct,
}: {
  listing: Listing;
  valuation: Valuation;
  comps: Comp[];
  deltaPct?: number | null;
}) {
  const [open, setOpen] = useState(false);

  const grouped = useMemo(() => {
    const byTier: Record<string, number[]> = { building: [], street: [], iris: [] };
    for (const c of comps) {
      if (c.price_per_m2 && c.price_per_m2 > 0 && byTier[c.tier]) {
        byTier[c.tier].push(c.price_per_m2);
      }
    }
    return byTier;
  }, [comps]);

  const adjustmentRows = Object.entries(valuation.adjustments || {});
  const topComps = useMemo(() => {
    const tierRank: Record<string, number> = { building: 0, street: 1, iris: 2, none: 9 };
    return [...comps]
      .filter((c) => c.price_per_m2 && c.price_per_m2 > 0)
      .sort((a, b) => {
        const ta = tierRank[a.tier] ?? 9;
        const tb = tierRank[b.tier] ?? 9;
        if (ta !== tb) return ta - tb;
        return new Date(b.date_mutation).getTime() - new Date(a.date_mutation).getTime();
      })
      .slice(0, 5);
  }, [comps]);

  function downloadHtmlReport() {
    const html = buildPrintableHtml({ listing, valuation, topComps, deltaPct });
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const slug = (listing.address_raw ?? listing.title ?? "estimation")
      .slice(0, 48)
      .replace(/[^\p{L}\p{N}]+/gu, "-")
      .replace(/^-|-$/g, "");
    a.href = url;
    a.download = `rapport-estimation-${slug || "paris-buyer-copilot"}.html`;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  /** Opens the system print dialog (user can choose « Enregistrer au format PDF »). Avoids popup blockers. */
  function printReport() {
    const html = buildPrintableHtml({ listing, valuation, topComps, deltaPct });
    const iframe = document.createElement("iframe");
    iframe.setAttribute("aria-hidden", "true");
    iframe.style.cssText =
      "position:fixed;right:0;bottom:0;width:0;height:0;border:0;opacity:0;pointer-events:none";
    document.body.appendChild(iframe);
    iframe.onload = () => {
      try {
        iframe.contentWindow?.focus();
        iframe.contentWindow?.print();
      } finally {
        setTimeout(() => {
          iframe.remove();
        }, 1000);
      }
    };
    iframe.srcdoc = html;
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-xs text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
      >
        <Info className="h-4 w-4" />
        Comprendre l&apos;estimation
      </button>

      {open ? (
        <div className="fixed inset-0 z-50 bg-black/40 p-4 md:p-8">
          <div className="mx-auto max-w-3xl rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 md:p-6 max-h-[90vh] overflow-auto">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-[var(--muted)]">
                  Détail du calcul
                </div>
                <h3 className="text-xl font-semibold mt-1">
                  Pourquoi cette estimation ?
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-[var(--muted)] hover:text-[var(--foreground)]"
              >
                <CircleX className="h-5 w-5" />
              </button>
            </div>
            <div className="mt-3 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={downloadHtmlReport}
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-1.5 text-xs text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
              >
                <Download className="h-4 w-4" />
                Télécharger le rapport (HTML)
              </button>
              <button
                type="button"
                onClick={printReport}
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-1.5 text-xs text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
              >
                <Printer className="h-4 w-4" />
                Imprimer ou enregistrer en PDF
              </button>
            </div>

            <section className="mt-5 space-y-2 text-sm">
              <Row k="Prix demandé" v={formatEur(listing.price_eur)} />
              <Row k="Prix estimé" v={formatEur(valuation.fair_value_eur)} />
              <Row
                k="Sur/sous-cote"
                v={`${formatPct(deltaPct)} (${valuation.fair_value_eur && listing.price_eur ? formatEur((listing.price_eur ?? 0) - valuation.fair_value_eur) : "—"})`}
              />
              <Row k="Confiance" v={valuation.confidence} />
              <Row k="Comparables retenus" v={`${valuation.n_comps} (${valuation.base_tier})`} />
            </section>

            <section className="mt-6">
              <h4 className="font-semibold text-sm mb-2">1) Données utilisées (DVF)</h4>
              <div className="space-y-2 text-sm text-[var(--muted)]">
                <TierLine label="Même immeuble" values={grouped.building} />
                <TierLine label="Même rue" values={grouped.street} />
                <TierLine label="Quartier / rayon 500m" values={grouped.iris} />
              </div>
            </section>

            <section className="mt-6">
              <h4 className="font-semibold text-sm mb-2">2) Ajustements appliqués</h4>
              {adjustmentRows.length === 0 ? (
                <p className="text-sm text-[var(--muted)]">Aucun ajustement explicite appliqué.</p>
              ) : (
                <div className="space-y-1 text-sm">
                  {adjustmentRows.map(([k, v]) => (
                    <Row
                      key={k}
                      k={prettyAdjustment(k)}
                      v={`${v.toFixed(2)}x (${v >= 1 ? "+" : ""}${((v - 1) * 100).toFixed(1)}%)`}
                    />
                  ))}
                </div>
              )}
            </section>

            <section className="mt-6">
              <h4 className="font-semibold text-sm mb-2">3) Formule simplifiée</h4>
              <p className="text-sm text-[var(--muted)] leading-relaxed">
                Prix estimé = (médiane €/m² des comparables pondérés par récence + similarité)
                × (surface du bien) × (ajustements).
              </p>
              <p className="text-sm text-[var(--muted)] leading-relaxed mt-2">
                Fourchette plausible:
                {" "}
                <span className="font-mono text-[var(--foreground)]">
                  {formatEur(valuation.fair_value_low_eur)} — {formatEur(valuation.fair_value_high_eur)}
                </span>
              </p>
            </section>

            <section className="mt-6">
              <h4 className="font-semibold text-sm mb-2">4) Top 5 comparables retenus</h4>
              {topComps.length === 0 ? (
                <p className="text-sm text-[var(--muted)]">Aucun comparable exploitable à afficher.</p>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
                  <table className="w-full text-xs">
                    <thead className="bg-[var(--accent-soft)] text-[var(--muted)] uppercase tracking-wider">
                      <tr>
                        <th className="text-left px-2 py-2 font-medium">Tier</th>
                        <th className="text-left px-2 py-2 font-medium">Adresse</th>
                        <th className="text-left px-2 py-2 font-medium">Date</th>
                        <th className="text-right px-2 py-2 font-medium">Prix</th>
                        <th className="text-right px-2 py-2 font-medium">€/m²</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topComps.map((c) => (
                        <tr key={`${c.id_mutation}-${c.tier}`} className="border-t border-[var(--border)]/50">
                          <td className="px-2 py-2 font-mono">{c.tier}</td>
                          <td className="px-2 py-2">{c.adresse ?? "—"}</td>
                          <td className="px-2 py-2 font-mono">{formatDate(c.date_mutation)}</td>
                          <td className="px-2 py-2 text-right font-mono">{formatEur(c.valeur_fonciere)}</td>
                          <td className="px-2 py-2 text-right font-mono">
                            {c.price_per_m2 ? `${Math.round(c.price_per_m2).toLocaleString("fr-FR")} €` : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="mt-6">
              <details className="rounded-lg border border-[var(--border)] px-3 py-2">
                <summary className="cursor-pointer text-sm font-semibold">
                  5) Hypothèses et limites
                </summary>
                <ul className="mt-3 list-disc pl-5 space-y-1 text-sm text-[var(--muted)]">
                  <li>Le modèle suppose que le bien est un appartement standard du marché parisien.</li>
                  <li>Les comparables DVF peuvent inclure des biais (état intérieur, nuisances, vue non observables).</li>
                  <li>La qualité dépend du nombre de ventes récentes proches et de la dispersion des €/m².</li>
                  <li>Si la confiance est faible, la fourchette est plus informative que la valeur centrale.</li>
                  <li>Le DPE et quelques attributs (étage/ascenseur) sont ajustés, mais pas tous les critères qualitatifs.</li>
                </ul>
              </details>
            </section>

            {valuation.rationale ? (
              <section className="mt-6">
                <h4 className="font-semibold text-sm mb-2">6) Note du moteur</h4>
                <p className="text-sm text-[var(--muted)] leading-relaxed">{valuation.rationale}</p>
              </section>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-[var(--border)]/50 py-1.5">
      <span className="text-[var(--muted)]">{k}</span>
      <span className="font-mono text-right">{v}</span>
    </div>
  );
}

function TierLine({ label, values }: { label: string; values: number[] }) {
  if (values.length === 0) {
    return <div>{label}: 0 comp</div>;
  }
  const med = median(values);
  return (
    <div>
      {label}: {values.length} comps · médiane{" "}
      <span className="font-mono text-[var(--foreground)]">{Math.round(med).toLocaleString("fr-FR")} €/m²</span>
    </div>
  );
}

function median(xs: number[]) {
  const s = [...xs].sort((a, b) => a - b);
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

function prettyAdjustment(k: string): string {
  return k
    .replaceAll("_", " ")
    .replace(/\bdpe\b/i, "DPE")
    .replace(/\bhigh\b/i, "haut")
    .replace(/\bfloor\b/i, "étage");
}

function buildPrintableHtml({
  listing,
  valuation,
  topComps,
  deltaPct,
}: {
  listing: Listing;
  valuation: Valuation;
  topComps: Comp[];
  deltaPct?: number | null;
}) {
  const rows = topComps
    .map(
      (c) => `
      <tr>
        <td>${escapeHtml(c.tier)}</td>
        <td>${escapeHtml(c.adresse ?? "—")}</td>
        <td>${escapeHtml(formatDate(c.date_mutation))}</td>
        <td style="text-align:right">${escapeHtml(formatEur(c.valeur_fonciere))}</td>
        <td style="text-align:right">${escapeHtml(c.price_per_m2 ? `${Math.round(c.price_per_m2).toLocaleString("fr-FR")} €` : "—")}</td>
      </tr>
    `,
    )
    .join("");

  return `<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <title>Explication d'estimation</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; color:#111; }
    h1 { margin: 0 0 8px; font-size: 22px; }
    h2 { margin: 18px 0 8px; font-size: 15px; }
    p, li { font-size: 12px; line-height: 1.45; }
    .muted { color:#555; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { border: 1px solid #ddd; padding: 6px; }
    th { background: #f3f6ff; text-align: left; }
  </style>
</head>
<body>
  <h1>Explication d'estimation</h1>
  <p class="muted">${escapeHtml(listing.title ?? "Annonce")} · ${escapeHtml(listing.address_raw ?? "Adresse inconnue")}</p>
  <h2>Résumé</h2>
  <ul>
    <li>Prix demandé: ${escapeHtml(formatEur(listing.price_eur))}</li>
    <li>Prix estimé: ${escapeHtml(formatEur(valuation.fair_value_eur))}</li>
    <li>Écart: ${escapeHtml(formatPct(deltaPct))}</li>
    <li>Confiance: ${escapeHtml(valuation.confidence)}</li>
    <li>Comparables retenus: ${valuation.n_comps} (${escapeHtml(valuation.base_tier)})</li>
  </ul>

  <h2>Top 5 comparables</h2>
  <table>
    <thead><tr><th>Tier</th><th>Adresse</th><th>Date</th><th>Prix</th><th>€/m²</th></tr></thead>
    <tbody>${rows || "<tr><td colspan='5'>Aucun comparable exploitable.</td></tr>"}</tbody>
  </table>

  <h2>Formule</h2>
  <p>Prix estimé = (médiane €/m² des comparables pondérés par récence + similarité) × surface × ajustements.</p>
  <p>Fourchette plausible: ${escapeHtml(formatEur(valuation.fair_value_low_eur))} — ${escapeHtml(formatEur(valuation.fair_value_high_eur))}</p>

  <h2>Hypothèses</h2>
  <ul>
    <li>Le bien est comparé à des appartements du même micro-marché.</li>
    <li>Les caractéristiques fines non observables (état, vue, bruit) peuvent créer un écart.</li>
    <li>La qualité de l'estimation augmente avec le nombre et la cohérence des comparables.</li>
  </ul>
</body>
</html>`;
}

function escapeHtml(s: string): string {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
