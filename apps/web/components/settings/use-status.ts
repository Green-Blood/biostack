import { useState } from "react";

export type Status = { text: string; ok: boolean } | null;

export const useStatus = () => useState<Status>(null);
