"use client";

import { useEffect, useState } from "react";
import { IconAdjustmentsHorizontal as AdjustmentsHorizontal, IconArrowRight as ArrowRight, IconBookmark as Bookmark, IconBuilding as Building, IconMapPin as MapPin, IconSearch as Search, IconSparkles as Sparkles, IconSquare as Square, IconStar as Star } from "@tabler/icons-react";
import Link from "next/link";
import { api, euro, Listing, SearchResponse, SearchResult } from "@/lib/api";

const examples = [
  "Тристаен във Велико Търново до 180 000 евро, поне 85 кв.м, не последен етаж",
  "Двустаен в Колю Фичето или Бузлуджа с асансьор и добра цена на квадрат",
  "Покажи ми най-добрите имоти за инвестиция във Велико Търново",
];

function scoreTone(score: number) { return score >= 80 ? "great" : score >= 60 ? "good" : score >= 40 ? "average" : "weak"; }

function ListingCard({ result, onFavorite }: { result: SearchResult; onFavorite: (listing: Listing) => void }) {
  const { listing, score, explanations } = result;
  const positives = explanations.filter((item) => item.status === "met").slice(0, 3);
  return <article className="listing-card">
    <div className="photo-wrap">
      {listing.primary_image ? <img src={listing.primary_image} alt="" /> : <div className="photo-placeholder"><Building size={42} /></div>}
      <button className={`favorite ${listing.is_favorite ? "active" : ""}`} aria-label="Любима" onClick={() => onFavorite(listing)}><Star size={20} fill={listing.is_favorite ? "currentColor" : "none"} /></button>
      <div className={`score-badge ${scoreTone(score)}`}><strong>{Math.round(score)}</strong><span>match</span></div>
    </div>
    <div className="listing-body">
      <div className="eyebrow"><MapPin size={15} /> {listing.district || "София"}</div>
      <h2>{listing.title}</h2>
      <div className="price-line"><strong>{euro(listing.price_eur)}</strong><span>{listing.price_per_sqm_eur ? `${Math.round(listing.price_per_sqm_eur).toLocaleString("bg-BG")} €/м²` : "няма цена/м²"}</span></div>
      <div className="facts">
        <span><Square size={16} /> {listing.area_sqm || "—"} м²</span>
        <span>{listing.room_count || "—"} стаи</span>
        <span>{listing.floor_number ?? listing.floor_label ?? "—"}/{listing.total_floors ?? "—"} етаж</span>
      </div>
      <div className="why">
        <span className="why-title"><Sparkles size={15} /> Защо е подходящ</span>
        {positives.map((item) => <p key={item.criterion}>✓ {item.explanation}</p>)}
      </div>
      <div className="card-actions">
        <Link className="primary-link" href={`/listings/${listing.id}`}>Виж детайли <ArrowRight size={17} /></Link>
        <button onClick={() => { const current = JSON.parse(localStorage.getItem("compare") || "[]"); localStorage.setItem("compare", JSON.stringify([...new Set([...current, listing.id])].slice(-4))); }}>+ Сравни</button>
        {listing.notes_count > 0 && <span className="note-count"><Bookmark size={15} /> {listing.notes_count}</span>}
      </div>
    </div>
  </article>;
}

export default function Home() {
  const [query, setQuery] = useState(examples[0]);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [favoritesOnly, setFavoritesOnly] = useState(false);

  async function runSearch() {
    setLoading(true); setError("");
    try { setData(await api<SearchResponse>("/api/searches", { method: "POST", body: JSON.stringify({ query, min_score: minScore, favorites_only: favoritesOnly }) })); }
    catch (err) { setError(err instanceof Error ? err.message : "Грешка"); }
    finally { setLoading(false); }
  }
  useEffect(() => { runSearch(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function favorite(listing: Listing) {
    await api(`/api/listings/${listing.id}/favorite`, { method: listing.is_favorite ? "DELETE" : "PUT" });
    if (data) setData({ ...data, results: data.results.map((r) => r.listing.id === listing.id ? { ...r, listing: { ...r.listing, is_favorite: !listing.is_favorite } } : r) });
  }

  return <div className="page-shell">
    <section className="hero">
      <div className="hero-copy"><div className="kicker"><Sparkles size={16} /> Имоти във Велико Търново</div><h1>Намери имота, който<br /><em>наистина ти пасва.</em></h1><p>Опиши какво търсиш във Велико Търново. Ще подредим офертите и ще обясним всяка препоръка.</p></div>
      <div className="search-panel">
        <label htmlFor="search">Какъв имот търсиш?</label>
        <textarea id="search" value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="search-footer"><span>Пиши свободно — бюджет, квартал, условия...</span><button onClick={runSearch} disabled={loading}><Search size={19} /> {loading ? "Анализирам..." : "Намери имоти"}</button></div>
        <div className="chips">{examples.map((example, i) => <button key={example} onClick={() => setQuery(example)}>Пример {i + 1}</button>)}</div>
      </div>
    </section>

    <section className="results-layout">
      <aside className="filters">
        <div className="filter-title"><AdjustmentsHorizontal size={19} /><strong>Бързи филтри</strong></div>
        <label>Минимален match <strong>{minScore}</strong></label>
        <input type="range" min="0" max="90" step="10" value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} />
        <label className="check"><input type="checkbox" checked={favoritesOnly} onChange={(e) => setFavoritesOnly(e.target.checked)} /><span>Само любими</span></label>
        <button className="apply" onClick={runSearch}>Приложи</button>
        {data && <div className="parsed"><span>Разбрана заявка</span>{Object.entries(data.parsed_criteria).filter(([, v]) => Array.isArray(v) ? v.length : Boolean(v)).map(([k, v]) => <p key={k}><strong>{k.replaceAll("_", " ")}</strong><br />{Array.isArray(v) ? v.join(", ") : String(v)}</p>)}</div>}
      </aside>
      <div className="results">
        <div className="results-head"><div><span className="section-label">ПОДБРАНИ ЗА ТЕБ</span><h2>{data?.results.length ?? 0} подходящи имота</h2></div><span className="sort">Подредени по match score</span></div>
        {error && <div className="error">{error}. Увери се, че backend-ът работи на порт 8000.</div>}
        {data?.results.map((result) => <ListingCard key={result.listing.id} result={result} onFavorite={favorite} />)}
      </div>
    </section>
  </div>;
}
