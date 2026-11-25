import Link from "next/link";
import { Plus } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";

/** The "+ Add visit" pill used on the Timeline and the Overview. Plain markup, so server pages can use it. */
export function AddVisitButton({ label, variant = "default" }: { label: string; variant?: "default" | "outline" }) {
  return <Link href="/records/new" className={buttonVariants({ variant, size: "lg" })}><Plus aria-hidden />{label}</Link>;
}
