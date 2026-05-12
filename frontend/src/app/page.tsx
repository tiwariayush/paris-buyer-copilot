"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { ClipboardPaste } from "lucide-react";

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
      <section className="flex-1 flex items-center justify-center px-6 md:px-12 py-16">
        <div className="w-full max-w-2xl">
          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight leading-[1.1]">
            Combien vaut{" "}
            <span className="text-[var(--accent)] italic">vraiment</span>{" "}
            cette annonce ?
          </h1>
          <p className="mt-4 text-base md:text-lg text-[var(--muted)] leading-relaxed">
            Commencez par le <strong className="font-medium text-[var(--foreground)]">lien</strong>{" "}
            de l&apos;annonce : nous téléchargeons la page HTML côté serveur et en extrayons prix, surface et adresse
            (données structurées ou analyse du texte de la page). Estimation transparente à partir des ventes notariales réelles à Paris.
          </p>
          <details className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2">
            <summary className="cursor-pointer text-sm text-[var(--muted)] list-none flex items-center gap-2 [&::-webkit-details-marker]:hidden">
              <ClipboardPaste className="h-4 w-4 text-[var(--accent)] shrink-0" />
              <span>Le site bloque ou la page est vide ? Utiliser le copier-coller</span>
            </summary>
            <p className="mt-2 text-sm text-[var(--muted)] leading-relaxed pl-6">
              Ouvrez l&apos;annonce dans votre navigateur, faites{" "}
              <span className="font-mono text-[var(--foreground)]">Cmd+A</span> puis{" "}
              <span className="font-mono text-[var(--foreground)]">Cmd+C</span>, et collez le texte à la place du lien.
            </p>
          </details>

          <form onSubmit={submit} className="mt-8 flex flex-col gap-3">
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={"https://www.bienici.com/annonce/...\n\n— si besoin : texte collé depuis la page —\n\n3 pièces 65m² rue de Rivoli Paris 1er, 850 000 €, 4e étage avec ascenseur, DPE D…"}
              rows={isUrl ? 2 : 8}
              className="w-full px-4 py-3 rounded-xl border border-[var(--border)] bg-[var(--card)] text-base focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-y font-sans"
              autoFocus
            />
            <p className="text-xs text-[var(--muted)]">
              En mode URL : privilégiez le lien direct vers l&apos;annonce. En mode texte : incluez prix, m², adresse ou code postal, étage et DPE si visibles.
            </p>
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
        </div>
      </section>

      <footer className="px-6 md:px-12 py-6 text-xs text-[var(--muted)] border-t border-[var(--border)]">
        Données : DVF géolocalisé (Etalab) · API DPE (ADEME) · Base Adresse
        Nationale · IRIS (INSEE) · IDFM · data.education.gouv.fr.
      </footer>
    </main>
  );
}
