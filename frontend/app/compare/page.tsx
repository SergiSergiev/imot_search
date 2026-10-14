"use client";

import { useEffect, useState } from "react";
import { IconScale as Scale, IconTrash as Trash } from "@tabler/icons-react";
import Link from "next/link";
import { api, euro, Listing } from "@/lib/api";

const rows: [string, (x: Listing) => string][] = [
  ["Цена", (x) => euro(x.price_eur)], ["Цена на м²", (x) => x.price_per_sqm_eur ? `${Math.round(x.price_per_sqm_eur)} €` : "—"],
  ["Локация", (x) => x.district || "—"], ["Площ", (x) => x.area_sqm ? `${x.area_sqm} м²` : "—"], ["Тип", (x) => x.property_type || "—"],
  ["Стаи", (x) => String(x.room_count || "—")], ["Етаж", (x) => `${x.floor_number ?? "—"} / ${x.total_floors ?? "—"}`], ["Състояние", (x) => x.condition || "—"],
];

export default function ComparePage() {
  const [items, setItems] = useState<Listing[]>([]);
  useEffect(() => { const ids: number[] = JSON.parse(localStorage.getItem("compare") || "[]"); Promise.all(ids.map((id) => api<Listing>(`/api/listings/${id}`))).then(setItems); }, []);
  function remove(id: number) { const next = items.filter((x) => x.id !== id); setItems(next); localStorage.setItem("compare", JSON.stringify(next.map((x) => x.id))); }
  return <div className="content-page"><div className="page-heading"><span className="section-label">СРАВНЕНИЕ</span><h1>Имот до имот</h1><p>Сравни до четири избрани оферти по най-важните показатели.</p></div>{items.length ? <div className="compare-wrap"><table className="compare-table"><thead><tr><th>Показател</th>{items.map((item) => <th key={item.id}><div className="compare-title">{item.primary_image && <img src={item.primary_image} alt="" />}<Link href={`/listings/${item.id}`}>{item.title}</Link><button onClick={() => remove(item.id)}><Trash size={16} /></button></div></th>)}</tr></thead><tbody>{rows.map(([label, value]) => <tr key={label}><th>{label}</th>{items.map((item) => <td key={item.id}>{value(item)}</td>)}</tr>)}</tbody></table></div> : <div className="empty-state"><Scale size={46} /><h2>Няма избрани имоти</h2><p>Добави имоти за сравнение от картите в резултатите.</p><Link href="/">Към търсенето</Link></div>}</div>;
}
