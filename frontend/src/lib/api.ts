import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('setu_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── Shared types ───────────────────────────────────────────────────────────────

export interface IntakeResult {
  needcard_id: string
  is_duplicate: boolean
  merged_into: string | null
  extraction_failed: boolean
  needs_review: boolean
  urgency_score: number
  need_type: string
}

export interface NeedCard {
  id: string
  need_type: string
  description_clean: string
  urgency_score_base: number
  urgency_score_eff: number
  urgency_reasoning: string
  affected_count: number | null
  skills_needed: string[]
  geo_lat: number
  geo_lng: number
  geo_confidence: number
  location_text_raw: string
  contact_name: string | null
  contact_detail: string | null
  report_count: number
  status: string
  needs_review: boolean
  extraction_failed: boolean
  created_at: string
  updated_at: string
}

export interface BriefResponse {
  dispatch_id: string
  brief_text: string
  brief_status: string
  map_link: string | null
  created_at: string
  language: string
  word_count: number
  generation_failed: boolean
}

// Mirrors backend DispatchRecord model
export interface DispatchRecord {
  id: string
  needcard_id: string
  volunteer_id: string
  match_score: number
  distance_km: number
  skill_overlap: string[]
  brief_text: string
  brief_status: string
  brief_edit_history: object[]
  status: 'pending' | 'accepted' | 'en_route' | 'completed' | 'cancelled'
  dispatched_at: string
  accepted_at: string | null
  completed_at: string | null
  cancelled_at: string | null
  cancellation_reason: string | null
}

// Mirrors backend Volunteer model
export interface Volunteer {
  id: string
  name: string
  phone: string
  language_pref: string
  skills: string[]
  current_lat: number
  current_lng: number
  availability: 'available' | 'busy' | 'offline'
  max_radius_km: number
  total_hours: number
  completed_missions: number
  current_dispatch_id: string | null
  fcm_token: string | null
  geohash_4: string
  geohash_5: string
  created_at: string
  updated_at: string
}

// ── NGO dashboard API calls ────────────────────────────────────────────────────

export const submitText = (text: string, submitter_id?: string) =>
  api.post<IntakeResult>('/intake/text', { text, submitter_id })

export const getNeedCard = (id: string) =>
  api.get<NeedCard>(`/needcards/${id}`)

export const listOpenNeedCards = () =>
  api.get<NeedCard[]>('/needcards?status=open&limit=50')

export const generateBrief = (dispatch_id: string) =>
  api.post<BriefResponse>(`/brief/${dispatch_id}`)

export const getBrief = (dispatch_id: string) =>
  api.get<BriefResponse>(`/brief/${dispatch_id}`)

// ── Volunteer app API calls ────────────────────────────────────────────────────

export const getDispatch = (dispatch_id: string) =>
  api.get<DispatchRecord>(`/dispatch/${dispatch_id}`)

export const acceptDispatch = (dispatch_id: string) =>
  api.post<DispatchRecord>(`/dispatch/${dispatch_id}/accept`)

export const enRouteDispatch = (dispatch_id: string) =>
  api.post<DispatchRecord>(`/dispatch/${dispatch_id}/en_route`)

export const completeDispatch = (dispatch_id: string) =>
  api.post<DispatchRecord>(`/dispatch/${dispatch_id}/complete`)

export const cancelDispatch = (dispatch_id: string, reason?: string) =>
  api.post<DispatchRecord>(`/dispatch/${dispatch_id}/cancel`, { reason })

export const getVolunteer = (volunteer_id: string) =>
  api.get<Volunteer>(`/volunteers/${volunteer_id}`)

export const getVolunteerHistory = (volunteer_id: string) =>
  api.get<DispatchRecord[]>(`/volunteers/${volunteer_id}/history`)

export default api