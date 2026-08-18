export const CATEGORIES = ['pothole', 'garbage', 'broken_streetlight', 'waterlogging', 'other']

export const CATEGORY_META = {
  pothole: { label: 'Pothole', color: '#f59e0b', icon: '⭕' },
  garbage: { label: 'Garbage', color: '#10b981', icon: '🗑️' },
  broken_streetlight: { label: 'Streetlight', color: '#facc15', icon: '💡' },
  waterlogging: { label: 'Waterlogging', color: '#38bdf8', icon: '🌊' },
  other: { label: 'Other', color: '#94a3b8', icon: '❔' },
}

export const STATUS_META = {
  open: { label: 'Open', color: '#f87171' },
  assigned: { label: 'Assigned', color: '#fb923c' },
  in_progress: { label: 'In Progress', color: '#facc15' },
  resolved: { label: 'Resolved', color: '#34d399' },
  rejected: { label: 'Rejected', color: '#64748b' },
}

export const DEPARTMENTS = {
  pothole: 'Roads & Infrastructure',
  garbage: 'Sanitation',
  broken_streetlight: 'Street Lighting',
  waterlogging: 'Drainage & Water',
  other: 'General Administration',
}

export function priorityBandColor(band) {
  return band === 1 ? '#f87171' : band === 2 ? '#fb923c' : '#38bdf8'
}

export function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso.replace(' ', 'T') + 'Z')
  return d.toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
