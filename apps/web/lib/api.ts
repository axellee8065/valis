/** Server-side fetchers against the live Valis API (Railway). */

const API = process.env.VALIS_API_URL ?? "https://valis-api-production.up.railway.app";

export type Stats = {
  transactions: number;
  properties: number;
  complexes: number;
  active_attestations: number;
  latest_model_id: string | null;
  data_range: { from: string; to: string };
  network: string;
};

export type Attestation = {
  attestation_uid: string;
  global_id: string;
  value_usd_cents: number;
  confidence_score_bps: number;
  ci_lower_usd_cents: number;
  ci_upper_usd_cents: number;
  model_id: string;
  issued_at: string;
  sui_tx_digest: string;
  admin_level_2: string | null;
  net_area_sqm: string | null;
  complex_name: string | null;
};

/** Baked fallbacks so the page renders even if the API is briefly down. */
export const FALLBACK_STATS: Stats = {
  transactions: 352_523,
  properties: 242_400,
  complexes: 8_533,
  active_attestations: 61,
  latest_model_id: "avm-kr-seoul-apt-v3-20260723-8fd9fd6",
  data_range: { from: "2020-01-01", to: "2026-07-23" },
  network: "sui:testnet",
};

/** Fallback for the Dubai demo (country=AE) until first live fetch. */
export const FALLBACK_STATS_AE: Stats = {
  transactions: 569_551,
  properties: 128_910,
  complexes: 3_296,
  active_attestations: 0,
  latest_model_id: "avm-ae-dubai-apt-v1",
  data_range: { from: "2003-06-02", to: "2024-08-22" },
  network: "sui:testnet",
};

export async function getStats(
  country?: string,
): Promise<{ stats: Stats; live: boolean }> {
  const qs = country ? `?country=${country}` : "";
  try {
    const res = await fetch(`${API}/v1/stats${qs}`, { next: { revalidate: 120 } });
    if (!res.ok) throw new Error(String(res.status));
    return { stats: (await res.json()) as Stats, live: true };
  } catch {
    return { stats: country === "AE" ? FALLBACK_STATS_AE : FALLBACK_STATS, live: false };
  }
}

export async function getAttestations(country?: string): Promise<Attestation[]> {
  const qs = country ? `&country=${country}` : "";
  try {
    const res = await fetch(`${API}/v1/attestations?limit=8${qs}`, {
      next: { revalidate: 120 },
    });
    if (!res.ok) throw new Error(String(res.status));
    return (await res.json()) as Attestation[];
  } catch {
    return [];
  }
}

export const fmtUsd = (cents: number) =>
  "$" + Math.round(cents / 100).toLocaleString("en-US");

export const fmtInt = (n: number) => n.toLocaleString("ko-KR");

export const shortHex = (h: string, head = 8, tail = 6) =>
  h.length > head + tail + 3 ? `${h.slice(0, head)}…${h.slice(-tail)}` : h;
