export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Listing = {
  id: number; agency_id: number; source_url: string; status: string; title: string;
  description: string; summary?: string | null; transaction_type: "sale" | "rent"; property_type?: string | null;
  room_count?: number | null; price_eur?: number | null; area_sqm?: number | null;
  price_per_sqm_eur?: number | null; city: string; district?: string | null;
  floor_number?: number | null; floor_label?: string | null; total_floors?: number | null;
  condition?: string | null; construction_type?: string | null; construction_age?: "new" | "old" | null; construction_year?: number | null;
  primary_image?: string | null; is_favorite: boolean; notes_count: number;
  first_seen_at: string; last_seen_at: string;
};

export type Explanation = {
  criterion: string; status: "met" | "partial" | "unmet" | "unknown";
  weight: number; points: number; actual_value?: string | null;
  expected_value?: string | null; explanation: string;
};

export type SearchResult = { listing: Listing; score: number; hard_criteria_passed: boolean; explanations: Explanation[] };
export type SearchResponse = { search_id: number; query: string; parsed_criteria: Record<string, unknown>; parser: string; answer: string; total_count: number; results: SearchResult[] };

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers }, cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Възникна грешка при заявката.");
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const euro = (value?: number | null) => value == null ? "—" : new Intl.NumberFormat("bg-BG", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(value);
