import React, { useEffect, useMemo, useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Circle } from 'react-leaflet'
import L from 'leaflet'
import { api } from '../api'
import { CATEGORIES, CATEGORY_META, STATUS_META, DEPARTMENTS, priorityBandColor, fmtTime } from '../constants'

const MARKER_SIZES = { 1: 14, 2: 18, 3: 22, 4: 26, 5: 30 }
const SEVERITY = { 1: '#34d399', 2: '#a3e635', 3: '#facc15', 4: '#fb923c', 5: '#f87171' }

function makeIcon(issue) {
  const size = MARKER_SIZES[Math.min(5, Math.ceil(Math.log2((issue.affected_count || 1) + 1) + 1))]
  const color = SEVERITY[Math.min(5, Math.max(1, Math.round(issue.severity || 3)))]
  return L.divIcon({
    className: '',
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2.5px solid rgba(255,255,255,0.9);box-shadow:0 0 16px ${color}88, 0 4px 10px rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center;font-size:${Math.max(9, size/2.2)}px;font-weight:700;color:rgba(0,0,0,0.75)">${issue.affected_count || 1}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

export default function Dashboard() {
  const [issues, setIssues] = useState([])
  const [filter, setFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const load = async () => {
    try {
      const qs = new URLSearchParams()
      if (filter) qs.set('category', filter)
      if (statusFilter) qs.set('status', statusFilter)
      const data = await api.listIssues(`?${qs}`)
      setIssues(data)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { load() }, [filter, statusFilter])

  const selectedData = useMemo(() => selected ? issues.find((i) => i.id === selected) : null, [selected, issues])

  const setStatus = async (id, status, dept) => {
    const issue = issues.find((i) => i.id === id)
    await api.setStatus(id, status, dept || issue?.dept || DEPARTMENTS[issue?.category] || 'General Administration')
    setRefreshing(true)
    load()
  }

  const ranked = useMemo(() => [...issues].sort((a, b) => b.priority_score - a.priority_score), [issues])

  return (
    <div className="h-screen flex flex-col bg-mesh relative overflow-hidden">
      <div className="absolute inset-0 pointer-events-none" aria-hidden>
        <div className="absolute top-[-30%] left-[20%] w-[60vw] h-[60vw] rounded-full bg-indigo-600/15 blur-3xl animate-float" />
        <div className="absolute bottom-[-40%] right-[10%] w-[55vw] h-[55vw] rounded-full bg-sky-500/10 blur-3xl animate-float" />
      </div>

      {/* Header */}
      <header className="glass z-20 border-x-0 border-t-0 px-5 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-sky-500 flex items-center justify-center font-display font-bold text-white shadow-glow">N</div>
          <div>
            <h1 className="font-display font-semibold text-lg leading-none">NagarAI Command</h1>
            <p className="text-[11px] text-slate-400">Ward Operations · Chennai</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="glass-chip px-3 py-1.5 text-xs text-slate-300">
            {issues.reduce((s, i) => s + (i.affected_count || 1), 0)} active complaints
          </span>
          <button onClick={() => { setRefreshing(true); load() }}
            className={`glass-chip px-3 py-1.5 text-xs hover:bg-white/15 transition ${refreshing ? 'opacity-50' : ''}`}>
            {refreshing ? '↻' : '↻ Refresh'}
          </button>
        </div>
      </header>

      <div className="flex flex-1 min-h-0 z-10">
        {/* Map */}
        <div className="flex-1 relative">
          <MapContainer center={[13.0827, 80.2707]} zoom={12} className="h-full w-full">
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {issues.map((i) => (
              <React.Fragment key={i.id}>
                {i.centroid_lat && (
                  <>
                    <Circle center={[i.centroid_lat, i.centroid_lng]} radius={60} pathOptions={{ color: SEVERITY[Math.min(5, Math.max(1, i.severity || 3))], fillColor: SEVERITY[Math.min(5, Math.max(1, i.severity || 3))], fillOpacity: 0.1, weight: 1 }} />
                    <Marker position={[i.centroid_lat, i.centroid_lng]} icon={makeIcon(i)} eventHandlers={{ click: () => setSelected(i.id) }}>
                      <Popup><div className="text-slate-800 font-medium text-sm">{i.summary}</div></Popup>
                    </Marker>
                  </>
                )}
              </React.Fragment>
            ))}
          </MapContainer>

          {/* Legend */}
          <div className="absolute top-3 right-3 glass rounded-xl p-3 text-xs space-y-1 z-[1000]">
            <div className="text-slate-300 font-medium mb-1">Severity</div>
            {[5, 4, 3, 2, 1].map((s) => (
              <div key={s} className="flex items-center gap-2">
                <span className="inline-block w-3 h-3 rounded-full" style={{ background: SEVERITY[s] }} />
                <span className="text-slate-400">{s}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Sidebar */}
        <div className="w-[380px] min-w-[320px] flex flex-col border-l border-white/10 bg-night/40 backdrop-blur-xl">
          {/* Filters */}
          <div className="p-3 border-b border-white/10 flex flex-wrap gap-1.5">
            <button onClick={() => setFilter('')} className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition ${!filter ? 'bg-indigo-600 text-white' : 'glass-chip text-slate-300 hover:bg-white/10'}`}>All</button>
            {CATEGORIES.map((c) => (
              <button key={c} onClick={() => setFilter(filter === c ? '' : c)}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition ${filter === c ? 'bg-indigo-600 text-white' : 'glass-chip text-slate-300 hover:bg-white/10'}`}>
                {CATEGORY_META[c].icon} {CATEGORY_META[c].label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
            {loading && <div className="text-center text-slate-400 text-sm py-10">Loading issues…</div>}
            {!loading && ranked.length === 0 && <div className="text-center text-slate-400 text-sm py-10">No issues match filters</div>}

            {ranked.map((issue) => {
              const band = (() => { try { return JSON.parse(issue.priority_reason || '{}').band } catch { return 3 } })()
              const sel = selected === issue.id
              const meta = CATEGORY_META[issue.category] || CATEGORY_META.other
              const statusMeta = STATUS_META[issue.status] || STATUS_META.open
              return (
                <div key={issue.id} onClick={() => setSelected(sel ? null : issue.id)}
                  className={`glass rounded-2xl p-3.5 cursor-pointer transition hover:bg-white/10 ${sel ? 'ring-2 ring-indigo-500/60' : ''}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-lg" style={{ background: `${meta.color}22`, border: `1px solid ${meta.color}55` }}>{meta.icon}</span>
                      <div className="min-w-0">
                        <div className="text-[11px] text-slate-400 uppercase tracking-wide">{meta.label} · {issue.status}</div>
                        <div className="text-sm font-medium truncate">{issue.summary}</div>
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="font-display font-bold text-lg leading-none" style={{ color: priorityBandColor(band) }}>{Math.round(issue.priority_score)}</div>
                      <div className="text-[10px] text-slate-500">band {band}</div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between mt-2.5 text-[11px] text-slate-400">
                    <span>👥 {issue.affected_count} citizens</span>
                    <span>📍 {issue.centroid_lat ? `${issue.centroid_lat.toFixed(3)}, ${issue.centroid_lng.toFixed(3)}` : 'no geo'}</span>
                    <span>🗓 {fmtTime(issue.created_at)}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Detail drawer */}
      {selectedData && (
        <div className="absolute inset-y-0 right-0 w-[420px] max-w-full z-30 flex">
          <div className="flex-1 bg-black/40 backdrop-blur-sm" onClick={() => setSelected(null)} />
          <div className="w-[420px] max-w-full glass-strong flex flex-col">
            <div className="p-4 border-b border-white/10 flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="w-10 h-10 rounded-xl flex items-center justify-center text-xl" style={{ background: `${CATEGORY_META[selectedData.category]?.color}22`, border: `1px solid ${CATEGORY_META[selectedData.category]?.color}55` }}>{CATEGORY_META[selectedData.category]?.icon}</span>
                  <div>
                    <h2 className="font-display font-semibold">Issue #{selectedData.id}</h2>
                    <p className="text-xs text-slate-400">{CATEGORY_META[selectedData.category]?.label} · {selectedData.status}</p>
                  </div>
                </div>
              </div>
              <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-white text-xl leading-none">✕</button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              <p className="text-sm text-slate-200">{selectedData.summary}</p>

              <div className="glass rounded-2xl p-4">
                <h3 className="text-xs uppercase tracking-wide text-slate-400 font-medium mb-3">Priority formula</h3>
                {(() => {
                  const r = (() => { try { return JSON.parse(selectedData.priority_reason || '{}') } catch { return {} } })()
                  const terms = [['Severity', 'S', r.S, 'model estimate'], ['Affected', 'P', r.P, r.explain?.P], ['Days', 'T', r.T, r.explain?.T], ['Proximity', 'L', r.L, r.explain?.L]]
                  return (
                    <div>
                      <div className="flex justify-between items-center mb-3">
                        <span className="text-[11px] text-slate-500">score = band(S) · rank = P×T×L</span>
                        <span className="font-display font-bold text-xl" style={{ color: priorityBandColor(r.band) }}>{Math.round(selectedData.priority_score)}<span className="text-xs text-slate-500">/100</span></span>
                      </div>
                      <div className="space-y-2">
                        {terms.map(([label, key, val, exp]) => (
                          <div key={key} className="flex items-center justify-between text-xs">
                            <span className="text-slate-400">{label} <b className="text-slate-200">{key}</b></span>
                            <span className="text-slate-200 font-mono">{typeof val === 'number' ? val.toFixed(2) : '—'}</span>
                          </div>
                        ))}
                      </div>
                      <div className="mt-3 pt-3 border-t border-white/10 text-[11px] text-slate-500 space-y-1">
                        <div>band {r.band} · {r.explain?.P}</div>
                        <div>{r.explain?.T}</div>
                        <div>{r.explain?.L}</div>
                      </div>
                    </div>
                  )
                })()}
              </div>

              <div className="glass rounded-2xl p-4">
                <h3 className="text-xs uppercase tracking-wide text-slate-400 font-medium mb-3">Why merged ({selectedData.members?.length || selectedData.affected_count} citizens)</h3>
                {(selectedData.members || []).map((m) => (
                  <div key={m.complaint_id} className="flex justify-between items-center text-xs py-1.5 border-b border-white/5 last:border-0">
                    <span className="text-slate-300">complaint #{m.complaint_id}</span>
                    <span className="text-slate-400 font-mono">sim {Math.round(m.sim_total * 100)}% (t{m.text_score?.toFixed(2)} g{m.geo_score?.toFixed(2)} v{m.vision_score?.toFixed(2)})</span>
                  </div>
                ))}
              </div>

              {selectedData.school_hospital_prox && (() => {
                try {
                  const pois = JSON.parse(selectedData.school_hospital_prox)
                  if (pois.length) return (
                    <div className="glass rounded-2xl p-4">
                      <h3 className="text-xs uppercase tracking-wide text-slate-400 font-medium mb-2">Nearby school/hospital</h3>
                      {pois.map((p, i) => <div key={i} className="text-xs text-slate-300 py-0.5">🏫 {p.kind}: {p.name}</div>)}
                    </div>
                  )
                } catch {}
                return null
              })()}
            </div>

            <div className="p-4 border-t border-white/10 space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                <span>Department: {selectedData.dept || DEPARTMENTS[selectedData.category] || '—'}</span>
                {selectedData.sla_deadline && <span>SLA: {fmtTime(selectedData.sla_deadline)}</span>}
              </div>
              <div className="grid grid-cols-3 gap-2">
                <button onClick={() => setStatus(selectedData.id, 'in_progress')} className="py-2 rounded-xl glass-chip text-xs font-medium hover:bg-white/15 transition">⏳ In Progress</button>
                <button onClick={() => setStatus(selectedData.id, 'resolved')} className="py-2 rounded-xl text-xs font-medium transition" style={{ background: '#065f46', border: '1px solid #34d39955' }}>✅ Resolve</button>
                <button onClick={() => setStatus(selectedData.id, 'rejected')} className="py-2 rounded-xl glass-chip text-xs font-medium hover:bg-white/15 transition">✕ Reject</button>
              </div>
              <a href={`/status/${selectedData.members?.[0]?.complaint_id || ''}`} className="block text-center text-xs text-slate-400 hover:text-slate-200 py-1">
                Share status link → notifies citizens
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
