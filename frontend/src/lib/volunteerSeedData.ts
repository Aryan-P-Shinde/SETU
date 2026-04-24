/**
 * volunteerSeedData.ts
 *
 * Demo data for the volunteer app view.
 * Mirrors the shape of DispatchRecord, Volunteer, and NeedCard
 * so the UI renders fully without a live backend.
 *
 * In production this data comes from:
 *   GET /brief/{dispatch_id}   → active dispatch + brief
 *   GET /volunteer/{id}        → volunteer profile
 *   GET /dispatch/history      → past missions (Phase 2)
 */

import type { DispatchRecord, Volunteer, NeedCard } from './api'

// ── Active dispatch (pending → volunteer sees this first) ─────────────────────

export const SEED_DISPATCHES: DispatchRecord[] = [
  {
    id: 'demo_dispatch_001',
    needcard_id: 'seed_nc_001',
    volunteer_id: 'seed_vol_003',
    match_score: 0.94,
    distance_km: 1.8,
    skill_overlap: ['search_rescue', 'logistics_boat_operator'],
    brief_text:
      'CRITICAL — Three people trapped on rooftop at 45 MG Road, near old post office, Ward 3. ' +
      'Flood water has risen to ground floor. They have had no food or water for 8 hours. ' +
      'Take a boat if available. Bring rope, torch, and life jackets. ' +
      'On arrival, contact Priya Sharma: 9876543210.',
    brief_status: 'sent',
    status: 'pending',
    dispatched_at: new Date(Date.now() - 8 * 60000).toISOString(),
    accepted_at: null,
    completed_at: null,
    cancelled_at: null,
    cancellation_reason: null,
    brief_edit_history: [],
  },
]

// ── Volunteer profile ──────────────────────────────────────────────────────────

export const SEED_VOLUNTEER: Volunteer = {
  id: 'seed_vol_003',
  name: 'Rahul Das',
  phone: '9800000000',
  language_pref: 'en',
  skills: ['search_rescue', 'logistics_boat_operator'],
  current_lat: 22.571,
  current_lng: 88.361,
  availability: 'busy',
  max_radius_km: 25,
  total_hours: 72.0,
  completed_missions: 22,
  current_dispatch_id: 'demo_dispatch_001',
  fcm_token: null,
  geohash_4: 'tgpf',
  geohash_5: 'tgpfq',
  created_at: new Date(Date.now() - 90 * 24 * 3600000).toISOString(),
  updated_at: new Date(Date.now() - 8 * 60000).toISOString(),
}

// ── NeedCards keyed by id (active dispatch + history) ─────────────────────────

export const SEED_NEEDCARDS_BY_ID: Record<string, NeedCard> = {
  seed_nc_001: {
    id: 'seed_nc_001',
    need_type: 'rescue',
    description_clean: 'Three people trapped on rooftop at 45 MG Road after flood waters rose. Ground floor submerged. No food or water for 8 hours.',
    urgency_score_base: 9.5,
    urgency_score_eff: 9.2,
    urgency_reasoning: 'Life threat: people stranded with rising water for 8+ hours.',
    affected_count: 3,
    skills_needed: ['search_rescue', 'logistics_boat_operator'],
    geo_lat: 22.572, geo_lng: 88.363,
    geo_confidence: 0.92,
    location_text_raw: '45 MG Road, near old post office, Ward 3',
    contact_name: 'Priya Sharma', contact_detail: '9876543210',
    report_count: 2, status: 'matched', needs_review: false, extraction_failed: false,
    created_at: new Date(Date.now() - 25 * 60000).toISOString(),
    updated_at: new Date(Date.now() - 8 * 60000).toISOString(),
  },

  // History cards
  seed_nc_h01: {
    id: 'seed_nc_h01',
    need_type: 'food',
    description_clean: '40 families in Ward 12 have had no food for 2 days. Children and elderly badly affected. Dry rations needed urgently.',
    urgency_score_base: 7.5, urgency_score_eff: 6.9,
    urgency_reasoning: '40 families, 2 days without food.',
    affected_count: 40, skills_needed: ['food_distribution'],
    geo_lat: 22.556, geo_lng: 88.347, geo_confidence: 0.85,
    location_text_raw: 'Ward 12, near government school',
    contact_name: 'Ramesh Kumar', contact_detail: '9887654321',
    report_count: 7, status: 'fulfilled', needs_review: false, extraction_failed: false,
    created_at: new Date(Date.now() - 48 * 3600000).toISOString(),
    updated_at: new Date(Date.now() - 40 * 3600000).toISOString(),
  },
  seed_nc_h02: {
    id: 'seed_nc_h02',
    need_type: 'water',
    description_clean: 'Drinking water supply contaminated after flooding. 55 people affected, children showing diarrhoea symptoms.',
    urgency_score_base: 8.5, urgency_score_eff: 7.8,
    urgency_reasoning: 'Water-borne illness developing in children.',
    affected_count: 55, skills_needed: ['water_purification'],
    geo_lat: 22.589, geo_lng: 88.402, geo_confidence: 0.78,
    location_text_raw: 'Mirpur Block D, House 15',
    contact_name: 'Meena Ghosh', contact_detail: '9001234567',
    report_count: 3, status: 'fulfilled', needs_review: false, extraction_failed: false,
    created_at: new Date(Date.now() - 72 * 3600000).toISOString(),
    updated_at: new Date(Date.now() - 60 * 3600000).toISOString(),
  },
  seed_nc_h03: {
    id: 'seed_nc_h03',
    need_type: 'rescue',
    description_clean: '80-year-old woman alone in flooded home, cannot walk. Needs evacuation.',
    urgency_score_base: 9.0, urgency_score_eff: 8.5,
    urgency_reasoning: 'Elderly, alone, mobility impaired, rising water.',
    affected_count: 1, skills_needed: ['search_rescue', 'elderly_care'],
    geo_lat: 22.54, geo_lng: 88.41, geo_confidence: 0.90,
    location_text_raw: '12 Patel Nagar, near water tank, Barrackpore',
    contact_name: 'Rajan (neighbour)', contact_detail: '9123456780',
    report_count: 2, status: 'fulfilled', needs_review: false, extraction_failed: false,
    created_at: new Date(Date.now() - 5 * 24 * 3600000).toISOString(),
    updated_at: new Date(Date.now() - 4.5 * 24 * 3600000).toISOString(),
  },
}

// ── Past mission history ───────────────────────────────────────────────────────

export const SEED_HISTORY: Array<{ dispatch: DispatchRecord; card: NeedCard }> = [
  {
    dispatch: {
      id: 'demo_dispatch_h01',
      needcard_id: 'seed_nc_h01',
      volunteer_id: 'seed_vol_003',
      match_score: 0.72,
      distance_km: 3.4,
      skill_overlap: ['search_rescue'],
      brief_text: 'HIGH — 40 families in Ward 12 need dry rations. Go to Ward 12, near government school.',
      brief_status: 'sent',
      status: 'completed',
      dispatched_at: new Date(Date.now() - 48 * 3600000).toISOString(),
      accepted_at: new Date(Date.now() - 47.5 * 3600000).toISOString(),
      completed_at: new Date(Date.now() - 44 * 3600000).toISOString(),
      cancelled_at: null,
      cancellation_reason: null,
      brief_edit_history: [],
    },
    card: SEED_NEEDCARDS_BY_ID['seed_nc_h01'],
  },
  {
    dispatch: {
      id: 'demo_dispatch_h02',
      needcard_id: 'seed_nc_h02',
      volunteer_id: 'seed_vol_003',
      match_score: 0.65,
      distance_km: 5.1,
      skill_overlap: ['search_rescue'],
      brief_text: 'HIGH — Contaminated water in Mirpur Block D. 55 people affected.',
      brief_status: 'sent',
      status: 'completed',
      dispatched_at: new Date(Date.now() - 72 * 3600000).toISOString(),
      accepted_at: new Date(Date.now() - 71.8 * 3600000).toISOString(),
      completed_at: new Date(Date.now() - 68 * 3600000).toISOString(),
      cancelled_at: null,
      cancellation_reason: null,
      brief_edit_history: [],
    },
    card: SEED_NEEDCARDS_BY_ID['seed_nc_h02'],
  },
  {
    dispatch: {
      id: 'demo_dispatch_h03',
      needcard_id: 'seed_nc_h03',
      volunteer_id: 'seed_vol_003',
      match_score: 0.91,
      distance_km: 2.2,
      skill_overlap: ['search_rescue'],
      brief_text: 'CRITICAL — Elderly woman needs evacuation at Patel Nagar.',
      brief_status: 'sent',
      status: 'completed',
      dispatched_at: new Date(Date.now() - 5 * 24 * 3600000).toISOString(),
      accepted_at: new Date(Date.now() - 5 * 24 * 3600000 + 10 * 60000).toISOString(),
      completed_at: new Date(Date.now() - 4.5 * 24 * 3600000).toISOString(),
      cancelled_at: null,
      cancellation_reason: null,
      brief_edit_history: [],
    },
    card: SEED_NEEDCARDS_BY_ID['seed_nc_h03'],
  },
]