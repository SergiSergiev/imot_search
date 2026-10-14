"use client";

import { use, useEffect, useState } from "react";
import { IconArrowLeft as ArrowLeft, IconCheck as Check, IconExternalLink as ExternalLink, IconMapPin as MapPin, IconMessagePlus as MessagePlus, IconSparkles as Sparkles, IconX as X } from "@tabler/icons-react";
import Link from "next/link";
import { api, euro, Explanation, Listing } from "@/lib/api";

type Detail = Listing & { images: { id: number; source_url: string }[]; features: { key: string; normalized_value: unknown; confidence: number }[]; notes: { id: number; body: string; created_at: string }[]; changes: { id: number; field_name: string; old_value?: string; new_value?: string; detected_at: string }[]; contact_name?: string; contact_phone?: string };
const featureNames: Record<string, string> = { elevator: "Асансьор", parking: "Паркиране", south_exposure: "Южно изложение", near_metro: "Близо до метро", furnished: "Обзаведен", new_construction: "Ново строителство", needs_renovation: "Нужда от ремонт" };

export default function ListingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params); const [listing, setListing] = useState<Detail | null>(null); const [note, setNote] = useState(""); const [analysis, setAnalysis] = useState<Explanation[]>([]);
  const load = () => api<Detail>(`/api/listings/${id}`).then(setListing);
  useEffect(() => { load(); api<{ results: { listing: Listing; explanations: Explanation[] }[] }>("/api/searches", { method: "POST", body: JSON.stringify({ query: "Покажи добри имоти в София" }) }).then((r) => setAnalysis(r.results.find((x) => x.listing.id === Number(id))?.explanations || [])); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  async function addNote(e: React.FormEvent) { e.preventDefault(); await api(`/api/listings/${id}/notes`, { method: "POST", body: JSON.stringify({ body: note }) }); setNote(""); load(); }
  if (!listing) return <div className="content-page">Зареждане...</div>;
  const positives = analysis.filter((x) => x.status === "met"); const risks = analysis.filter((x) => ["unmet", "unknown"].includes(x.status));
  return <div className="content-page detail-page">
    <Link href="/" className="back"><ArrowLeft size={18} /> Обратно към резултатите</Link>
    <div className="gallery">{listing.images.slice(0, 3).map((img, index) => <img key={img.id} className={index === 0 ? "main-photo" : ""} src={img.source_url} alt="" />)}{listing.images.length === 0 && <div className="photo-placeholder">Няма снимки</div>}</div>
    <div className="detail-grid">
      <article>
        <div className="eyebrow"><MapPin size={15} /> {listing.district || "София"}</div><h1>{listing.title}</h1>
        <div className="detail-price"><strong>{euro(listing.price_eur)}</strong><span>{listing.price_per_sqm_eur ? `${Math.round(listing.price_per_sqm_eur)} €/м²` : "—"}</span></div>
        <div className="spec-grid"><div><span>Площ</span><strong>{listing.area_sqm || "—"} м²</strong></div><div><span>Стаи</span><strong>{listing.room_count || "—"}</strong></div><div><span>Етаж</span><strong>{listing.floor_number ?? "—"} / {listing.total_floors ?? "—"}</strong></div><div><span>Строителство</span><strong>{listing.construction_type || "—"}</strong></div><div><span>Година</span><strong>{listing.construction_year || "—"}</strong></div><div><span>Състояние</span><strong>{listing.condition || "—"}</strong></div></div>
        <section className="detail-section"><h2>Описание</h2><p>{listing.description || "Няма налично описание."}</p></section>
        <section className="detail-section"><h2>Характеристики</h2><div className="feature-tags">{listing.features.map((feature) => <span key={feature.key}>{feature.normalized_value ? <Check size={15} /> : <X size={15} />} {featureNames[feature.key] || feature.key}</span>)}</div></section>
        <section className="detail-section"><h2>История на промените</h2>{listing.changes.length ? listing.changes.map((change) => <div className="history-row" key={change.id}><span>{new Date(change.detected_at).toLocaleDateString("bg-BG")}</span><strong>{change.field_name}</strong><span>{change.old_value} → {change.new_value}</span></div>) : <p className="muted">Все още няма засечени промени.</p>}</section>
      </article>
      <aside className="detail-side">
        <div className="analysis-card"><div className="analysis-head"><Sparkles /><div><span>AI АНАЛИЗ</span><strong>Силни страни и рискове</strong></div></div><h3>Плюсове</h3>{positives.slice(0, 4).map((x) => <p className="positive" key={x.criterion}><Check size={16} /> {x.explanation}</p>)}<h3>За проверка</h3>{risks.slice(0, 4).map((x) => <p className="risk" key={x.criterion}><X size={16} /> {x.explanation}</p>)}</div>
        <div className="notes-card"><h2>Лични бележки</h2>{listing.notes.map((item) => <div className="note" key={item.id}>{item.body}<span>{new Date(item.created_at).toLocaleDateString("bg-BG")}</span></div>)}<form onSubmit={addNote}><textarea required value={note} onChange={(e) => setNote(e.target.value)} placeholder="Напр. Да се провери шумът от булеварда..." /><button><MessagePlus size={17} /> Добави бележка</button></form></div>
        <a className="original-link" href={listing.source_url} target="_blank" rel="noreferrer">Отвори оригиналната обява <ExternalLink size={17} /></a>
      </aside>
    </div>
  </div>;
}
