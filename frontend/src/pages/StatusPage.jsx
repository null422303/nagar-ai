import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import { CATEGORY_META, STATUS_META, DEPARTMENTS, fmtTime } from '../constants'

const STATUS_STEPS = ['open', 'assigned', 'in_progress', 'resolved']

export default function StatusPage() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getStatus(id).then(setData).catch((e) => setError(String(e.message || e))).finally(() => setLoading(false))
  }, [id])

  if (loading) return <div className="min-h-screen bg-mesh flex items-center justify-center text-slate-400">Loading…</div>
  if (error || !data) return (
    <div className="min-h-screen bg-mesh flex flex-col items-center justify-center text-slate-400">
      <div className="text-5xl mb-4">🔍</div>
      <p>Complaint not found</p>
    </div>
  )

  const issue = data.issue
  const meta = CATEGORY_META[data.category] || CATEGORY_META.other
  const stepIdx = STATUS_STEPS.indexOf(data.status)
  const resolved = data.status === 'resolved'

  return (
    <div className="min-h-screen bg-mesh flex items-center justify-center p-6 relative overflow-hidden">
      <div className="absolute top-[-20%] left-[-10%] w-[50vw] h-[50vw] rounded-full bg-indigo-600/20 blur-3xl animate-float" aria-hidden />
      <div className="absolute bottom-[-30%] right-[-15%] w-[60vw] h-[60vw] rounded-full bg-sky-500/10 blur-3xl animate-float" aria-hidden />

      <div className="glass-strong rounded-3xl p-8 max-w-md w-full relative z-10">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl" style={{ background: `${meta.color}22`, border: `1px solid ${meta.color}55` }}>{meta.icon}</div>
          <div>
            <h1 className="font-display text-xl font-semibold">Complaint #{data.id}</h1>
            <p className="text-xs text-slate-400">{meta.label} · filed {fmtTime(data.created_at)}</p>
          </div>
        </div>

        <div className="glass rounded-2xl p-4 mb-5 text-sm text-slate-200">{data.summary}</div>

        {/* status steps */}
        <div className="flex items-center mb-6">
          {STATUS_STEPS.map((s, i) => (
            <React.Fragment key={s}>
              <div className="flex flex-col items-center flex-1">
                <div className={`w-9 h-9 rounded-full flex items-center justify-center text-sm border-2 transition ${i <= stepIdx ? 'bg-emerald-500 border-emerald-400 text-white' : 'border-slate-600 text-slate-500'}`}>
                  {i < stepIdx || resolved ? '✓' : i + 1}
                </div>
                <span className={`text-[10px] mt-1 ${i <= stepIdx ? 'text-emerald-300' : 'text-slate-500'}`}>{STATUS_META[s].label}</span>
              </div>
              {i < STATUS_STEPS.length - 1 && <div className={`h-0.5 flex-1 -mt-5 ${i < stepIdx ? 'bg-emerald-500' : 'bg-slate-700'}`} />}
            </React.Fragment>
          ))}
        </div>

        {resolved && (
          <div className="glass rounded-2xl p-4 mb-4 text-center border border-emerald-400/30">
            <div className="text-3xl mb-1">🎉</div>
            <p className="text-sm text-emerald-300 font-medium">This issue has been resolved by the corporation.</p>
          </div>
        )}

        <div className="space-y-2 text-xs">
          <div className="flex justify-between"><span className="text-slate-400">Department</span><span className="text-slate-200">{data.dept || DEPARTMENTS[data.category] || 'Pending routing'}</span></div>
          <div className="flex justify-between"><span className="text-slate-400">Severity</span><span className="text-slate-200">{data.severity}/5</span></div>
          {issue && <div className="flex justify-between"><span className="text-slate-400">Part of issue #{issue.id}</span><span className="text-slate-200">👥 {issue.affected_count} citizens affected</span></div>}
        </div>

        <a href="/" className="block w-full text-center mt-6 py-3 rounded-xl glass-chip text-sm hover:bg-white/15 transition">Report another issue</a>
      </div>
    </div>
  )
}
