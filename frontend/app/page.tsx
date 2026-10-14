"use client";

import { useEffect, useState } from "react";
import { IconAdjustmentsHorizontal as AdjustmentsHorizontal, IconArrowRight as ArrowRight, IconBookmark as Bookmark, IconBuilding as Building, IconMapPin as MapPin, IconSearch as Search, IconSparkles as Sparkles, IconSquare as Square, IconStar as Star } from "@tabler/icons-react";
import Link from "next/link";
import { api, euro, Listing, SearchResponse, SearchResult } from "@/lib/api";

const examples = [
  "Търся инвестиционен апартамент, подценен спрямо сходните в квартала. Предпочитам ново строителство, но приемам старо, ако цената на кв.м е поне 15% под медианата и не е за основен ремонт. Изключи партер и последен етаж.",
  "Намери семеен тристаен до 280 000 евро в тих район, близо до парк и училище. Накажи обявите до голям булевард и отбележи къде липсва информация за шум, асансьор или паркиране.",
  "Кои двустайни под наем изглеждат най-изгодни спрямо площта, обзавеждането и квартала, но имат подозрително кратко или неясно описание?",
  "Сравни ново и старо строителство в Лозенец и Хладилника. При старото допусни ремонт до 20 000 евро и обясни кога по-ниската цена компенсира риска.",
  "Покажи обяви, които вероятно са пренебрегнати: лоши снимки или липсващи данни, но добра цена на квадрат, тераса и нормален етаж. Подготви въпроси към брокера.",
  "Кои обяви не казват дали има асансьор, година на строителство или паркомясто, въпреки че са на висок етаж и над средната цена за квартала?",
];

function scoreTone(score: number) { return score >= 80 ? "great" : score >= 60 ? "good" : score >= 40 ? "average" : "weak"; }
const transactionLabel = (value: Listing["transaction_type"]) => value === "rent" ? "Под наем" : "Продажба";
const constructionLabel = (value: Listing["construction_age"]) => value === "new" ? "Ново строителство" : value === "old" ? "Старо строителство" : "Строителство неуточнено";

function ListingCard({ result, onFavorite }: { result: SearchResult; onFavorite: (listing: Listing) => void }) {
  const { listing, score, explanations } = result;
  const concerns = explanations.filter((item) => ["unmet", "unknown", "partial"].includes(item.status)).slice(0, 4);
  const positives = explanations.filter((item) => item.status === "met").slice(0, 2);
  const analysis = [...positives, ...concerns].slice(0, 6);
  return <article className="listing-card">
    <div className="photo-wrap">
      {listing.primary_image ? <img src={listing.primary_image} alt="" /> : <div className="photo-placeholder"><Building size={42} /></div>}
      <button className={`favorite ${listing.is_favorite ? "active" : ""}`} aria-label="Любима" onClick={() => onFavorite(listing)}><Star size={20} fill={listing.is_favorite ? "currentColor" : "none"} /></button>
      <div className={`score-badge ${scoreTone(score)}`}><strong>{Math.round(score)}</strong><span>match</span></div>
    </div>
    <div className="listing-body">
      <div className="eyebrow"><MapPin size={15} /> {listing.district || "София"}</div>
      <div className="listing-tags"><span>{transactionLabel(listing.transaction_type)}</span><span>{constructionLabel(listing.construction_age)}</span></div>
      <h2>{listing.title}</h2>
      <div className="price-line"><strong>{euro(listing.price_eur)}</strong><span>{listing.price_per_sqm_eur ? `${Math.round(listing.price_per_sqm_eur).toLocaleString("bg-BG")} €/м²` : "няма цена/м²"}</span></div>
      <div className="facts">
        <span><Square size={16} /> {listing.area_sqm || "—"} м²</span>
        <span>{listing.room_count || "—"} стаи</span>
        <span>{listing.floor_number ?? listing.floor_label ?? "—"}/{listing.total_floors ?? "—"} етаж</span>
      </div>
      <p className="listing-summary">{(listing.summary || listing.description || "Няма подробно описание.").slice(0, 260)}{(listing.summary || listing.description || "").length > 260 ? "…" : ""}</p>
      <div className="why">
        <span className="why-title"><Sparkles size={15} /> Обяснение на оценката</span>
        {analysis.map((item) => <p className={`reason-${item.status}`} key={item.criterion}>{item.status === "met" ? "✓" : item.status === "unmet" ? "−" : "?"} {item.explanation}</p>)}
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
  const [transactionType, setTransactionType] = useState("");
  const [constructionAge, setConstructionAge] = useState("");

  async function runSearch() {
    setLoading(true); setError("");
    try { setData(await api<SearchResponse>("/api/searches", { method: "POST", body: JSON.stringify({ query, min_score: minScore, favorites_only: favoritesOnly, transaction_type: transactionType || null, construction_age: constructionAge || null }) })); }
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
      <div className="hero-copy"><div className="kicker"><Sparkles size={16} /> Имоти в София</div><h1>Намери имота, който<br /><em>наистина ти пасва.</em></h1><p>Опиши какво търсиш в София. Ще подредим офертите и ще обясним всяка препоръка.</p></div>
      <div className="search-panel">
        <label htmlFor="search">Какъв имот търсиш?</label>
        <textarea id="search" value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="search-footer"><span>Пиши свободно — бюджет, квартал, условия...</span><button onClick={runSearch} disabled={loading}><Search size={19} /> {loading ? "Анализирам..." : "Намери имоти"}</button></div>
        <div className="chips">{examples.map((example, i) => <button key={example} title={example} onClick={() => setQuery(example)}>Сложна заявка {i + 1}</button>)}</div>
      </div>
    </section>

    <section className="results-layout">
      <aside className="filters">
        <div className="filter-title"><AdjustmentsHorizontal size={19} /><strong>Бързи филтри</strong></div>
        <label>Минимален match <strong>{minScore}</strong></label>
        <input type="range" min="0" max="90" step="10" value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} />
        <label htmlFor="transaction-type">Вид сделка</label>
        <select id="transaction-type" value={transactionType} onChange={(e) => setTransactionType(e.target.value)}><option value="">Всички</option><option value="sale">Продажба</option><option value="rent">Под наем</option></select>
        <label htmlFor="construction-age">Строителство</label>
        <select id="construction-age" value={constructionAge} onChange={(e) => setConstructionAge(e.target.value)}><option value="">Всички</option><option value="new">Ново</option><option value="old">Старо</option></select>
        <label className="check"><input type="checkbox" checked={favoritesOnly} onChange={(e) => setFavoritesOnly(e.target.checked)} /><span>Само любими</span></label>
        <button className="apply" onClick={runSearch}>Приложи</button>
        {data && <div className="parsed"><span>Разбрана заявка</span>{Object.entries(data.parsed_criteria).filter(([, v]) => Array.isArray(v) ? v.length : Boolean(v)).map(([k, v]) => <p key={k}><strong>{k.replaceAll("_", " ")}</strong><br />{Array.isArray(v) ? v.join(", ") : String(v)}</p>)}</div>}
      </aside>
      <div className="results">
        <div className="results-head"><div><span className="section-label">ПОДБРАНИ ЗА ТЕБ</span><h2>{data?.total_count ?? 0} подходящи имота</h2>{data && data.total_count > data.results.length && <small>Показани са топ {data.results.length} резултата</small>}</div><span className="sort">Подредени по match score</span></div>
        {error && <div className="error">{error}. Увери се, че backend-ът работи на порт 8000.</div>}
        {data?.answer && <div className="local-answer"><Sparkles size={18} /><div><strong>Локален анализ</strong><p>{data.answer}</p></div></div>}
        {data?.results.map((result) => <ListingCard key={result.listing.id} result={result} onFavorite={favorite} />)}
      </div>
    </section>
  </div>;
}
