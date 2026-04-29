import { Suspense } from "react";
import VerdictView from "./view";

export const dynamic = "force-dynamic";

export default function VerdictPage() {
  return (
    <Suspense fallback={<Skeleton />}>
      <VerdictView />
    </Suspense>
  );
}

function Skeleton() {
  return (
    <div className="flex-1 flex items-center justify-center text-[var(--muted)]">
      Chargement…
    </div>
  );
}
