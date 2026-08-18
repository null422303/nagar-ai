import React from 'react'
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom'
import Intake from './pages/Intake.jsx'
import Dashboard from './pages/Dashboard.jsx'
import StatusPage from './pages/StatusPage.jsx'

function Gate() {
  const nav = useNavigate()
  return (
    <div className="min-h-screen bg-mesh flex items-center justify-center relative overflow-hidden">
      <div className="absolute top-[-20%] left-[-5%] w-[40vw] h-[40vw] rounded-full bg-indigo-600/25 blur-3xl animate-float" aria-hidden />
      <div className="absolute bottom-[-25%] right-[-8%] w-[45vw] h-[45vw] rounded-full bg-sky-500/15 blur-3xl animate-float" aria-hidden />
      <div className="glass-strong rounded-3xl p-10 w-full max-w-sm text-center relative z-10">
        <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-indigo-500 to-sky-500 flex items-center justify-center font-display font-bold text-3xl text-white shadow-glow mb-4">N</div>
        <h1 className="font-display text-2xl font-bold tracking-tight mb-1">NagarAI</h1>
        <p className="text-slate-400 text-sm mb-8">Civic Complaint Intelligence</p>
        <div className="space-y-3">
          <button onClick={() => nav('/report')} className="w-full py-3.5 rounded-xl font-semibold bg-gradient-to-r from-indigo-600 to-sky-500 hover:opacity-90 transition shadow-glow">
            🏛️ File a complaint
          </button>
          <button onClick={() => nav('/dashboard')} className="w-full py-3.5 rounded-xl font-semibold glass-chip hover:bg-white/15 transition">
            🗺️ Official dashboard
          </button>
        </div>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Gate />} />
        <Route path="/report" element={<Intake />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/status/:id" element={<StatusPage />} />
      </Routes>
    </BrowserRouter>
  )
}
