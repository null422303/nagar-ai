import React, { useState, useRef, useEffect } from 'react'
import { api } from '../api'

export default function Intake({ onDone }) {
  const [mode, setMode] = useState('text') // text | voice | photo | mix
  const [text, setText] = useState('')
  const [language, setLanguage] = useState('')
  const [recording, setRecording] = useState(false)
  const [audioBlob, setAudioBlob] = useState(null)
  const [audioExt, setAudioExt] = useState('wav')
  const [photo, setPhoto] = useState(null)
  const [gps, setGps] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const recRef = useRef(null)
  const chunksRef = useRef([])

  useEffect(() => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      (p) => setGps({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => {}, { timeout: 8000 },
    )
  }, [])

  useEffect(() => {
    if (!loading) return
    const iv = setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => clearInterval(iv)
  }, [loading])

  const startRec = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      chunksRef.current = []
      rec.ondataavailable = (e) => chunksRef.current.push(e.data)
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: rec.mimeType })
        setAudioBlob(blob)
        setAudioExt(rec.mimeType.includes('webm') ? 'webm' : 'wav')
      }
      rec.start()
      recRef.current = rec
      setRecording(true)
    } catch (e) {
      setError('Microphone access denied')
    }
  }
  const stopRec = () => {
    recRef.current?.stop()
    setRecording(false)
  }

  const submit = async () => {
    setError('')
    setLoading(true)
    setElapsed(0)
    try {
      const fd = new FormData()
      if (text.trim()) fd.append('text', text)
      if (language) fd.append('language', language)
      if (audioBlob) fd.append('audio', audioBlob, `voice.${audioExt}`)
      if (photo) fd.append('image', photo, photo.name)
      if (gps) { fd.append('lat', gps.lat); fd.append('lng', gps.lng) }
      const r = await api.fileComplaint(fd)
      setResult(r)
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setLoading(false)
    }
  }

  if (result) {
    const c = result.complaint
    const d = result.dedup
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-6 bg-mesh relative overflow-hidden">
        <div className="absolute top-[-20%] left-[-10%] w-[50vw] h-[50vw] rounded-full bg-indigo-600/20 blur-3xl animate-float" aria-hidden />
        <div className="absolute bottom-[-30%] right-[-15%] w-[60vw] h-[60vw] rounded-full bg-sky-500/10 blur-3xl animate-float" aria-hidden />
        <div className="glass-strong rounded-3xl p-8 max-w-lg w-full text-center relative z-10">
          <div className="text-5xl mb-4 animate-float">✅</div>
          <h1 className="font-display text-2xl font-semibold mb-1">Complaint filed</h1>
          <p className="text-slate-400 mb-6">Thank you — our AI understood it and routed it to the right queue.</p>
          <div className="glass rounded-2xl p-5 text-left mb-6 space-y-2">
            <Row k="Category" v={c.category} cap />
            <Row k="Severity" v={`${c.severity}/5`} />
            <Row k="Summary" v={c.summary} />
            <Row k="Location" v={c.lat ? `${c.lat.toFixed(4)}, ${c.lng.toFixed(4)}` : 'needs pin'} />
            {d.merged && <Row k="Dedup" v={`Merged with existing issue #${d.issue_id} (sim ${Math.round(d.scores?.sim * 100)}%)`} accent />}
            {!d.merged && <Row k="Status" v={`New issue #${d.issue_id}`} accent />}
          </div>
          <a href={`/status/${c.id}`} className="block w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 transition font-medium mb-3">
            Track status
          </a>
          <button onClick={() => { setResult(null); setText(''); setAudioBlob(null); setPhoto(null) }} className="w-full py-2 text-sm text-slate-400 hover:text-slate-200 transition">
            File another
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center min-h-screen p-6 bg-mesh relative overflow-hidden">
      <div className="absolute top-[-15%] left-[-10%] w-[45vw] h-[45vw] rounded-full bg-indigo-600/20 blur-3xl animate-float" aria-hidden />
      <div className="absolute bottom-[-25%] right-[-12%] w-[50vw] h-[50vw] rounded-full bg-sky-500/10 blur-3xl animate-float" aria-hidden />
      <div className="glass-strong rounded-3xl p-8 w-full max-w-lg relative z-10">
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">🏛️</div>
          <h1 className="font-display text-3xl font-bold tracking-tight">Report a civic issue</h1>
          <p className="text-slate-400 text-sm mt-1">Voice, photo, or text — in any language. Our AI does the rest.</p>
        </div>

        <div className="flex gap-2 mb-6">
          {[['text', '✍️ Text'], ['voice', '🎤 Voice'], ['photo', '📷 Photo']].map(([m, l]) => (
            <button key={m} onClick={() => setMode(m)}
              className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition border ${mode === m ? 'bg-indigo-600 border-indigo-400/50 shadow-glow' : 'glass-chip text-slate-300 hover:bg-white/10'}`}>
              {l}
            </button>
          ))}
        </div>

        {mode === 'voice' && (
          <div className="space-y-4">
            <div className={`flex flex-col items-center py-8 ${recording ? '' : ''}`}>
              <button onClick={recording ? stopRec : startRec}
                className={`w-20 h-20 rounded-full flex items-center justify-center text-3xl transition ${recording ? 'bg-red-500 animate-pulse-ring' : 'bg-red-500/90 hover:bg-red-400'}`}>
                {recording ? '⏹' : '🎤'}
              </button>
              <p className="text-sm text-slate-400 mt-3">{recording ? 'Recording… tap to stop' : 'Tap and speak (Tamil, Hindi, English)'}</p>
            </div>
            {audioBlob && <div className="glass rounded-xl p-3 text-sm text-emerald-300 text-center">✓ Voice captured ({Math.round(audioBlob.size / 1024)} KB)</div>}
          </div>
        )}

        {mode === 'photo' && (
          <div className="space-y-4">
            <label className="glass-chip rounded-xl p-6 flex flex-col items-center cursor-pointer hover:bg-white/10 transition">
              <span className="text-4xl mb-2">📷</span>
              <span className="text-sm text-slate-300">{photo ? photo.name : 'Tap to take or choose a photo'}</span>
              <input type="file" accept="image/*" capture="environment" className="hidden"
                onChange={(e) => setPhoto(e.target.files?.[0] || null)} />
            </label>
            {photo && <img src={URL.createObjectURL(photo)} alt="preview" className="rounded-xl max-h-48 mx-auto" />}
          </div>
        )}

        <textarea value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Describe the issue… (e.g. 'anna nagar la periya pothole, school kitta')"
          className="w-full mt-4 p-3.5 rounded-xl bg-white/5 border border-white/10 focus:border-indigo-400/60 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 min-h-24 text-sm resize-none" />

        <div className="flex items-center justify-between mt-4 gap-3">
          <select value={language} onChange={(e) => setLanguage(e.target.value)}
            className="glass-chip rounded-lg px-3 py-2 text-sm text-slate-300 focus:outline-none">
            <option value="">Auto language</option>
            <option value="ta">தமிழ் (Tamil)</option>
            <option value="hi">हिन्दी (Hindi)</option>
            <option value="en">English</option>
          </select>
          <span className="text-xs text-slate-500">
            {gps ? '📍 GPS shared' : '📍 no GPS'}
          </span>
        </div>

        {error && <p className="text-red-400 text-sm mt-3">{error}</p>}

        <button onClick={submit} disabled={loading || (!text.trim() && !audioBlob && !photo)}
          className={`w-full mt-5 py-3.5 rounded-xl font-semibold transition ${loading || (!text.trim() && !audioBlob && !photo) ? 'bg-slate-700/60 text-slate-400 cursor-not-allowed' : 'bg-gradient-to-r from-indigo-600 to-sky-500 hover:opacity-90 shadow-glow'}`}>
          {loading ? `Analyzing… ${elapsed}s` : '🚀 File complaint'}
        </button>
        <p className="text-center text-[11px] text-slate-500 mt-3">Anonymous option · your data stays on the civic server</p>
      </div>
    </div>
  )
}

function Row({ k, v, cap, accent }) {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <span className="text-slate-400">{k}</span>
      <span className={`text-right font-medium ${accent ? 'text-emerald-300' : 'text-slate-200'}`}>
        {cap ? String(v).replace(/_/g, ' ') : v}
      </span>
    </div>
  )
}
