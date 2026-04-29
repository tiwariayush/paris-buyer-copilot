"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

const URL_RE = /^\s*https?:\/\/[^\s]+\s*$/i;

export default function Home() {
  const [content, setContent] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const isUrl = URL_RE.test(content);
  const showSourceInput = !isUrl && content.trim().length > 0;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const c = content.trim();
    if (!c) return setError("Collez une URL ou une annonce.");
    if (!isUrl && c.length < 60) {
      setError("Le texte est trop court — copiez la page complète de l'annonce (Cmd+A puis Cmd+C).");
      return;
    }
    // Stash content in sessionStorage to avoid huge URL params.
    const id = crypto.randomUUID();
    sessionStorage.setItem(
      `analyze:${id}`,
      JSON.stringify({ content: c, source_url: sourceUrl || null }),
    );
    startTransition(() => {
      router.push(`/verdict?id=${id}`);
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
            Collez l&apos;URL d&apos;une annonce — ou si le portail bloque (SeLoger,
            LeBonCoin&hellip;), <em>copiez l&apos;annonce elle-même</em>{" "}
            (<kbd className="font-mono text-xs px-1 py-0.5 rounded bg-[var(--accent-soft)] text-[var(--accent)]">⌘A ⌘C</kbd>{" "}
            sur la page) et collez tout ici.
          </p>

          <form onSubmit={submit} className="mt-8 flex flex-col gap-3">
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={"https://www.bienici.com/annonce/...\n\n— ou —\n\n3 pièces 65m² rue de Rivoli Paris 1er, 850 000 €, 4e étage avec ascenseur, DPE D…"}
              rows={isUrl ? 2 : 8}
              className="w-full px-4 py-3 rounded-xl border border-[var(--border)] bg-[var(--card)] text-base focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-y font-sans"
              autoFocus
            />
            {showSourceInput ? (
              <input
                type="url"
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
                placeholder="URL d'origine (optionnel — pour rappel dans le verdict)"
                className="w-full px-4 py-2 rounded-xl border border-[var(--border)] bg-[var(--card)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              />
            ) : null}
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs text-[var(--muted)] font-mono">
                {isUrl
                  ? "URL détectée · récupération + analyse"
                  : content
                    ? `${content.length} caractères · extraction par IA`
                    : ""}
              </span>
              <button
                type="submit"
                disabled={pending || !content}
                className="px-5 py-3 rounded-xl bg-[var(--accent)] text-white font-medium tracking-tight disabled:opacity-50 hover:opacity-90 transition-opacity"
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
