"use client";

import { useEffect, useState } from "react";
import { IconBuildingCommunity as BuildingCommunity, IconCheck as Check, IconDatabaseImport as DatabaseImport, IconLink as LinkIcon, IconLoader2 as Loader2, IconTrash as Trash } from "@tabler/icons-react";
import { api } from "@/lib/api";

type Agency = { id: number; name: string; source_url: string; import_status: string; last_successful_import_at?: string; listing_count: number };
type Job = { id: number; status: string; discovered: number; processed: number; created: number; updated: number; failed: number; error?: string };

export default function AgenciesPage() {
  const [agencies, setAgencies] = useState<Agency[]>([]); const [name, setName] = useState(""); const [url, setUrl] = useState(""); const [job, setJob] = useState<Job | null>(null); const [message, setMessage] = useState("");
  const load = () => api<Agency[]>("/api/agencies").then(setAgencies).catch(() => setMessage("Backend-ът не е достъпен."));
  useEffect(() => { void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  async function addAgency(e: React.FormEvent) { e.preventDefault(); try { await api("/api/agencies", { method: "POST", body: JSON.stringify({ name, source_url: url }) }); setName(""); setUrl(""); setMessage("Агенцията е добавена."); load(); } catch (err) { setMessage(err instanceof Error ? err.message : "Грешка"); } }
  async function startImport(id: number) { try { const created = await api<Job>(`/api/agencies/${id}/imports`, { method: "POST" }); setJob(created); const timer = setInterval(async () => { const next = await api<Job>(`/api/imports/${created.id}`); setJob(next); if (["completed", "failed"].includes(next.status)) { clearInterval(timer); load(); } }, 1200); } catch (err) { setMessage(err instanceof Error ? err.message : "Грешка"); } }
  async function removeAgency(agency: Agency) { if (!window.confirm(`Да изтрия ли „${agency.name}“ и всички нейни обяви?`)) return; try { await api(`/api/agencies/${agency.id}`, { method: "DELETE" }); setMessage("Агенцията и свързаните обяви са изтрити."); load(); } catch (err) { setMessage(err instanceof Error ? err.message : "Грешка"); } }
  return <div className="content-page">
    <div className="page-heading"><span className="section-label">ИЗТОЧНИЦИ</span><h1>Агенции и импорт</h1><p>Добави оторизиран профил на агенция в imot.bg. Импортът е бавен умишлено и спира при ограничение от сайта.</p></div>
    <div className="agency-grid">
      <form className="panel agency-form" onSubmit={addAgency}><div className="panel-icon"><BuildingCommunity /></div><h2>Добави агенция</h2><label>Име на агенцията<input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} placeholder="Напр. Домика" /></label><label>URL на профила<div className="input-icon"><LinkIcon size={18} /><input required type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://agency.imot.bg/" /></div></label><button className="button-primary" type="submit">Добави агенция</button><p className="fine-print">Добавяй само профили, за които имаш право на достъп и обработка.</p></form>
      <div className="panel agency-list"><h2>Добавени агенции</h2>{agencies.map((agency) => <div className="agency-row" key={agency.id}><div className="agency-avatar">{agency.name.slice(0, 1)}</div><div><strong>{agency.name}</strong><span>{agency.listing_count} обяви · {agency.import_status}</span></div><div className="agency-actions"><button onClick={() => startImport(agency.id)} disabled={agency.import_status === "running"}><DatabaseImport size={18} /> Извлечи</button><button className="delete-button" onClick={() => removeAgency(agency)} aria-label={`Изтрий ${agency.name}`}><Trash size={17} /></button></div></div>)}{agencies.length === 0 && <p>Все още няма агенции.</p>}</div>
    </div>
    {message && <div className="toast"><Check size={18} /> {message}</div>}
    {job && <div className="import-status"><div>{job.status === "running" ? <Loader2 className="spin" /> : <Check />}<div><strong>{job.status === "completed" ? "Импортът приключи" : job.status === "failed" ? "Импортът е спрян" : "Извличане на обяви"}</strong><span>{job.processed} от {job.discovered} обработени · {job.created} нови · {job.updated} променени</span></div></div><progress value={job.processed} max={Math.max(job.discovered, 1)} />{job.error && <p className="error">{job.error}</p>}</div>}
  </div>;
}
