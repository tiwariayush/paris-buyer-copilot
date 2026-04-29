"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

const SAMPLE = "https://www.bienici.com/annonce/...";

export default function Home() {
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!/^https?:\/\//i.test(url)) {
      setError("Collez une URL d'annonce complète (https://…)");
      return;
    }
    const encoded = encodeURIComponent(url);
    startTransition(() => {
      router.push(`/verdict?url=${encoded}`);
    });
  }

  return (
    <main className="flex-1 flex flex-col">
      <header className="px-6 md:px-12 py-6 border-b border-[var(--border)]">
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm tracking-tight text-[var(--accent)]">
            paris.copilot
          </span>
          <span className="text-xs text-[var(--muted)]">·</span>
          <span className="text-xs text-[var(--muted)] font-mono">
            DVF · DPE · BAN · IRIS
          </span>
        </div>
      </header>

      <section className="flex-1 flex items-center justify-center px-6 md:px-12 py-16">
        <div className="w-full max-w-2xl">
          <div className="text-xs uppercase tracking-[0.2em] text-[var(--accent)] font-semibold mb-3">
            Buyer copilot
          </div>
          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight leading-[1.05]">
            Combien vaut <em className="italic">vraiment</em> cette annonce&nbsp;?
          </h1>
          <p className="mt-4 text-base md:text-lg text-[var(--muted)] leading-relaxed">
            Collez n&apos;importe quelle annonce — Bien&apos;ici, SeLoger, LeBonCoin, PAP —
            et obtenez en quelques secondes la valeur de marché, les ventes
            comparables du même immeuble, le DPE, et un argumentaire de
            négociation. Tout est basé sur les données publiques de l&apos;État.
          </p>

          <form onSubmit={submit} className="mt-8 flex flex-col gap-3">
            <label htmlFor="url" className="sr-only">
              URL de l&apos;annonce
            </label>
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                id="url"
                type="url"
                placeholder={SAMPLE}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="flex-1 px-4 py-3 rounded-xl border border-[var(--border)] bg-[var(--card)] text-base focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-[var(--accent)] transition-shadow"
                autoFocus
              />
              <button
                type="submit"
                disabled={pending || !url}
                className="px-5 py-3 rounded-xl bg-[var(--accent)] text-white font-medium tracking-tight disabled:opacity-50 hover:bg-[var(--accent)]/90 transition-colors"
              >
                {pending ? "Analyse…" : "Analyser"}
              </button>
            </div>
            {error ? (
              <p className="text-sm text-[var(--negative)]">{error}</p>
            ) : null}
          </form>

          <div className="mt-12 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <Bullet
              title="Mêmes ventes que les notaires"
              body="DVF — toutes les transactions notariales depuis 2014."
            />
            <Bullet
              title="DPE intégré"
              body="Classes F/G = travaux obligatoires = levier de prix réel."
            />
            <Bullet
              title="Aucune commission"
              body="Vous repartez avec une argumentation que les agents ne peuvent pas masquer."
            />
          </div>
        </div>
      </section>

      <footer className="px-6 md:px-12 py-6 text-xs text-[var(--muted)] border-t border-[var(--border)]">
        Données : DVF géolocalisé (Etalab) · API DPE (ADEME) · Base Adresse
        Nationale · IRIS (INSEE) · IDFM · data.education.gouv.fr.
      </footer>
    </main>
  );
}

function Bullet({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-3">
      <div className="font-semibold text-sm text-[var(--foreground)]">{title}</div>
      <div className="mt-1 text-[var(--muted)] leading-relaxed">{body}</div>
    </div>
  );
}
