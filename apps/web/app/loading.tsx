import { Skeleton } from "@/components/ui/skeleton";

/** Shown while a page fetches its data: a calm header and two card-shaped blocks, in theme colours. */
export default function Loading() {
  return (
    <div className="space-y-8" role="status" aria-busy="true">
      <div className="space-y-3">
        <Skeleton className="h-9 w-56" />
        <Skeleton className="h-4 w-full max-w-md" />
      </div>
      <Skeleton className="h-40 w-full rounded-xl" />
      <div className="grid gap-4 sm:grid-cols-2">
        <Skeleton className="h-28 rounded-xl" />
        <Skeleton className="h-28 rounded-xl" />
      </div>
    </div>
  );
}
