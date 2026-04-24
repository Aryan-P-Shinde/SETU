"""
Seed script — populates Firestore with realistic demo data.
Idempotent: running twice yields the same state (uses fixed IDs).

Usage:
    cd backend
    FIREBASE_PROJECT_ID=your-project python scripts/seed.py
    FIREBASE_PROJECT_ID=your-project python scripts/seed.py --reset  # wipe first

Covers:
    - 50 NeedCards: all need_types, all urgency levels, mixed status
    - 30 Volunteers: spread across demo region (Kolkata + surrounds)
    - Edge cases: high report_count, needs_review=True, null geo
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from google.cloud import firestore
from app.models.needcard import NeedCard, NeedType, NeedStatus, SourceChannel
from app.models.volunteer import Volunteer, AvailabilityStatus

# FIX: was importing from app.services.firestore_repo which doesn't exist.
# Constants live in app.db.firestore_client.
from app.db.firestore_client import COL_NEED_CARDS, COL_VOLUNTEERS

# ── Demo region: Kolkata + surrounds ─────────────────────────────────────────
# Bounding box approx: lat 22.4–22.7, lng 88.2–88.5

NEED_CARDS_SEED = [
    # id suffix, need_type, desc, urgency_base, urgency_eff, affected, skills, lat, lng,
    # geo_conf, loc_text, contact_name, contact_detail, report_count, status, needs_review
    ("nc_001", "rescue",    "3 people trapped on rooftop at MG Road after flood water rose 6 feet. Been there 8 hours. No food/water.",
     9.5, 9.5, 3, ["search_rescue","logistics_boat_operator"], 22.5726, 88.3639, 0.9,
     "45 MG Road near old post office, Kolkata", "Priya", "9876543210", 1, "open", False),

    ("nc_002", "food",      "40 families in Ward 12 with no food for 2 days. Children crying. Dry rations needed urgently.",
     7.5, 6.8, 40, ["food_distribution"], 22.5958, 88.3247, 0.85,
     "Ward 12, Shyamnagar, North 24 Parganas", "Ramesh Kumar", "9988776655", 5, "open", False),

    ("nc_003", "medical",   "Pregnant woman about to deliver. Hospital road blocked by flood. Needs doctor immediately.",
     9.8, 9.8, 1, ["medical_doctor","medical_nurse"], 22.5200, 88.3800, 0.75,
     "Andheri colony, near railway crossing, South Kolkata", None, None, 1, "open", False),

    ("nc_004", "water",     "Drinking water contaminated after flood. 50+ people. Children showing signs of diarrhoea.",
     8.0, 7.2, 50, ["water_purification","water_distribution"], 22.6100, 88.4200, 0.88,
     "Block D, Mirpur area, Barasat", "Suresh", "8800112233", 3, "open", False),

    ("nc_005", "shelter",   "Family of 6 including 3-month-old baby and 2 elderly. House collapsed last night.",
     8.5, 8.0, 6, ["logistics_coordination"], 22.5500, 88.2900, 0.82,
     "Near Durga Mandir, Sector 5, Howrah", "Meena", "7654321098", 1, "open", False),

    ("nc_006", "logistics", "200 boxes dry rations at Industrial Area warehouse need transport to Stadium Ground relief camp.",
     4.0, 3.7, None, ["logistics_driver"], 22.5800, 88.3500, 0.95,
     "Plot 7, Industrial Estate Phase 3, Kolkata", "Suresh Babu", "8800112233", 1, "open", False),

    ("nc_007", "rescue",    "80-year-old woman alone in flooded home. Cannot walk. Needs evacuation.",
     9.0, 8.5, 1, ["search_rescue","elderly_care"], 22.5400, 88.4100, 0.90,
     "12 Patel Nagar, near water tank, Barrackpore", "Rajan (neighbour)", "9123456780", 2, "open", False),

    ("nc_008", "medical",   "Child snake bite in Mohalla Purana Qila. 8-year-old boy. Antivenom needed. No vehicle.",
     9.5, 9.5, 1, ["medical_paramedic","logistics_driver"], 22.4900, 88.3200, 0.70,
     "Mohalla Purana Qila, Uluberia", "Father", "9000123456", 1, "open", False),

    ("nc_009", "other",     "200 flood survivors at camp need psychological counselling. Especially children with trauma.",
     5.0, 4.5, 200, ["mental_health_counseling","child_care"], 22.5650, 88.3450, 0.92,
     "Saddar Hospital Relief Camp, Kolkata", None, None, 1, "open", False),

    ("nc_010", "rescue",    "25 people stranded in Nalkoop Gali. Water level rising. Boat needed urgently.",
     8.5, 8.0, 25, ["logistics_boat_operator","search_rescue"], 22.6300, 88.4500, 0.68,
     "Nalkoop wali Gali, Kasba Ghat, Kolkata", None, None, 7, "open", False),

    ("nc_011", "food",      "15 infants 0-6 months. No baby formula available anywhere in the area. Urgent.",
     9.0, 8.8, 15, ["food_distribution","child_care"], 22.5300, 88.3700, 0.0,
     "Location unknown - contact for details", None, "9871234567", 1, "open", True),

    ("nc_012", "shelter",   "School roof collapsed. 300 students have no shelter now. Building safety unknown.",
     6.5, 6.0, 300, ["structural_assessment","logistics_coordination"], 22.5750, 88.3900, 0.87,
     "Near City Bus Stand, Ward 3, Dum Dum", None, None, 2, "open", False),

    ("nc_013", "rescue",    "Building collapse at Industrial Estate. ~50 workers trapped under debris.",
     10.0, 10.0, 50, ["search_rescue","medical_paramedic","debris_clearance"], 22.5050, 88.2800, 0.94,
     "Plot 7, Industrial Estate Phase 3, Kolkata", None, None, 1, "open", False),

    ("nc_014", "other",     "Live electrical wires hanging over flood water in New Colony. Children nearby. Dangerous.",
     9.0, 8.5, None, ["engineering_electrical"], 22.5500, 88.3300, 0.85,
     "New Colony main road, Behala, Kolkata", None, None, 1, "open", False),

    ("nc_015", "logistics", "Relief camp coordinator lost contact with 3 field teams. Need radio/satellite comms setup.",
     7.0, 6.5, None, ["communications","logistics_coordination"], 22.5700, 88.3600, 0.93,
     "District Collectorate, Kolkata", None, None, 1, "open", False),

    ("nc_016", "other",     "Flood victims lost Aadhaar, ration cards, land records. Need legal aid for document recovery.",
     4.0, 3.8, None, ["legal_aid"], 22.5900, 88.4300, 0.80,
     "Kalyanpur village, North 24 Parganas", None, None, 1, "open", False),

    ("nc_017", "medical",   "80-year-old heart attack at 2am. No hospital open within 30km. Immediate help needed.",
     9.8, 9.8, 1, ["medical_doctor","logistics_driver"], 22.5100, 88.3100, 0.88,
     "House 5, Gali 3, Ram Colony, Howrah", None, None, 1, "open", False),

    ("nc_018", "food",      "20 families in Rajiv Nagar with no food. Children and elderly.",
     6.5, 5.9, 20, ["food_distribution"], 22.6200, 88.4400, 0.78,
     "Rajiv Nagar, near the school, Barasat", None, "9988776655", 3, "open", False),

    ("nc_019", "water",     "200 people in Mohana village. Cyclone destroyed everything. Drinking from puddles.",
     9.5, 9.5, 200, ["water_purification","water_distribution","food_distribution"], 22.4800, 88.2700, 0.65,
     "Mohana village, Sundarbans area", None, None, 4, "open", False),

    ("nc_020", "medical",   "Several diabetic patients at relief camp ran out of insulin. Life-threatening.",
     9.2, 9.2, None, ["medical_doctor","medical_nurse"], 22.5600, 88.3800, 0.91,
     "Nehru Stadium Relief Camp, Kolkata", None, None, 1, "open", False),

    # Fulfilled
    ("nc_021", "food",      "50 families needed food in Bhatpara. Fulfilled by volunteer team.",
     7.0, 0.5, 50, ["food_distribution"], 22.8900, 88.3900, 0.90,
     "Bhatpara, North 24 Parganas", None, None, 8, "fulfilled", False),

    ("nc_022", "medical",   "Medical aid delivered to Ward 7. Case closed.",
     8.0, 0.3, 15, ["medical_first_aid"], 22.5720, 88.3650, 0.88,
     "Ward 7, Chandannagar, Hooghly", "Priya", "9876543210", 1, "fulfilled", False),

    # Matched (in-progress)
    ("nc_023", "rescue",    "Family stranded on roof at Lake Town. Volunteer en route.",
     8.5, 8.0, 4, ["search_rescue"], 22.5900, 88.3900, 0.87,
     "Lake Town Block A, Kolkata", None, "9800011122", 1, "matched", False),

    # Stale
    ("nc_024", "logistics", "Old supply request - no longer needed.",
     2.0, 0.1, None, ["logistics_driver"], 22.5700, 88.3500, 0.85,
     "Salt Lake, Kolkata", None, None, 1, "stale", False),

    # Needs review
    ("nc_025", "other",     "[Extraction failed — raw input preserved for manual review]",
     5.0, 5.0, None, [], 0.0, 0.0, 0.0,
     "", None, None, 1, "open", True),

    ("nc_026", "food",      "Help needed at Gandhi Nagar. People are suffering. Exact need unclear.",
     5.0, 4.8, None, ["food_distribution"], 22.5450, 88.3250, 0.35,
     "Gandhi Nagar (approximate)", None, None, 1, "open", True),

    ("nc_027", "water",     "100 families without drinking water in Titagarh. Contaminated well.",
     7.5, 7.0, 100, ["water_purification"], 22.7400, 88.3800, 0.89,
     "Titagarh, North 24 Parganas", "Muniyasami", "9444321234", 2, "open", False),

    ("nc_028", "medical",   "30 people with fever and diarrhoea. Need medicines and medical team.",
     6.5, 6.0, 30, ["medical_first_aid","medical_doctor"], 22.5350, 88.2950, 0.82,
     "Village Khurd, near the school", "Sunita Devi", "8012345678", 1, "open", True),

    ("nc_029", "shelter",   "75 families stranded in Wadala village, Kolkata outskirts. No shelter, flood water inside.",
     8.0, 7.5, 75, ["logistics_boat_operator","logistics_coordination"], 22.6500, 88.4700, 0.77,
     "Wadala village, outskirts of Barasat", "Gram sevak Mahesh", "9765432100", 3, "open", False),

    ("nc_030", "other",     "40 unaccompanied children at Nehru Stadium camp. Parents missing. Need care and supervision.",
     7.5, 7.0, 40, ["child_care","mental_health_counseling","food_distribution"], 22.5600, 88.3800, 0.91,
     "Nehru Stadium Relief Camp, Kolkata", None, None, 1, "open", False),

    ("nc_031", "medical",   "Voice transcript: filler words cleaned. Fatima recently gave birth. Needs hospital transport.",
     7.5, 7.2, 2, ["medical_nurse","logistics_driver"], 22.5500, 88.3400, 0.72,
     "Lal Bagh area, Kolkata", "Fatima", None, 1, "open", False),

    ("nc_032", "rescue",    "Bridge washed out. 15 families stranded in Rampur. 2 people injured. No food.",
     8.0, 7.6, 15, ["search_rescue","medical_first_aid","food_distribution"], 22.4700, 88.2600, 0.65,
     "Rampur village, near washed-out bridge", "Meena", "7654321098", 2, "open", False),

    ("nc_033", "food",      "Night emergency - 35 people at temporary camp with no dinner arrangements.",
     6.0, 5.5, 35, ["food_distribution","food_cooking"], 22.5800, 88.4000, 0.88,
     "Temporary camp, Sector 8, Salt Lake", None, "9011223344", 1, "open", False),

    ("nc_034", "logistics", "Supply coordination needed. Multiple relief camps running low simultaneously.",
     6.5, 6.0, None, ["logistics_coordination","communications"], 22.5700, 88.3600, 0.90,
     "Central coordination, District Office, Kolkata", None, None, 1, "open", False),

    ("nc_035", "medical",   "Elderly man with chest pain at Ultadanga. Family cannot transport him.",
     9.0, 8.7, 1, ["medical_paramedic","medical_doctor"], 22.5850, 88.3950, 0.87,
     "Ultadanga, near water reservoir, Kolkata", None, "9311445566", 1, "open", False),

    ("nc_036", "water",     "Tube well broken. 60 people relying on it for drinking water. No alternatives.",
     6.0, 5.5, 60, ["water_distribution"], 22.6000, 88.4100, 0.83,
     "Madhyamgram village, North 24 Parganas", None, "9988001122", 1, "open", False),

    ("nc_037", "shelter",   "Temporary tarpaulin shelter collapsed in rain. 20 people now without cover at night.",
     7.0, 6.5, 20, ["logistics_coordination"], 22.5450, 88.3100, 0.80,
     "Open ground near Karunamoyee, Salt Lake", None, None, 2, "open", False),

    ("nc_038", "other",     "Translation needed. Tamil-speaking survivors cannot communicate with local relief workers.",
     5.0, 4.8, 15, ["translation_tamil","logistics_coordination"], 22.5700, 88.3650, 0.85,
     "Relief camp, Howrah Station area", None, None, 1, "open", False),

    ("nc_039", "food",      "Diabetic patients need specific food. Regular rations unsuitable. 10 patients.",
     7.0, 6.5, 10, ["food_distribution","medical_nurse"], 22.5550, 88.3750, 0.88,
     "Primary school relief camp, Belgharia", "Camp doctor", "9800554433", 1, "open", False),

    ("nc_040", "rescue",    "Boat needed to check on isolated village. No contact for 3 days since cyclone.",
     8.5, 8.0, None, ["logistics_boat_operator","search_rescue"], 22.4500, 88.2400, 0.55,
     "Gosaba island, Sundarbans (approximate)", None, None, 1, "open", True),

    ("nc_041", "medical",   "Wound infection getting worse. Patient needs antibiotics and dressing change.",
     6.5, 6.0, 1, ["medical_first_aid","medical_nurse"], 22.5300, 88.3500, 0.87,
     "Tent 14, Rabindra Sarani relief camp, Kolkata", "Patient family", "9977331155", 1, "open", False),

    ("nc_042", "logistics", "Motorcycle needed to deliver medicine to 3 small camps not accessible by car.",
     5.5, 5.0, None, ["logistics_driver"], 22.5600, 88.3400, 0.90,
     "Coordination from Shyambazar, Kolkata", None, "9866223311", 1, "open", False),

    ("nc_043", "food",      "Bengali-English report: 30 people dorkar khana. No food since morning.",
     6.5, 6.2, 30, ["food_distribution"], 22.5750, 88.3850, 0.82,
     "Camp near Dakshineswar, Kolkata", None, None, 2, "open", False),

    ("nc_044", "shelter",   "Pregnant woman and family need safe shelter. Current shelter has no roof.",
     8.5, 8.2, 3, ["logistics_coordination","medical_nurse"], 22.5400, 88.3200, 0.85,
     "Open area near Jadavpur, Kolkata", "Husband", "9988112233", 1, "open", False),

    ("nc_045", "water",     "Water tanker needed. 5 villages sharing one source, all contaminated.",
     7.5, 7.0, 300, ["water_distribution","water_purification"], 22.6700, 88.4800, 0.72,
     "Cluster of villages near Basirhat, North 24 Parganas", "Block officer", "9766554433", 3, "open", False),

    ("nc_046", "medical",   "Dialysis patient missed 2 sessions. Critical. Machine or transport to hospital needed.",
     9.5, 9.5, 1, ["medical_doctor","logistics_driver"], 22.5200, 88.3600, 0.90,
     "Behala, South Kolkata", "Family", "9311667788", 1, "open", False),

    ("nc_047", "other",     "Civil engineer needed. Assess if 3 buildings are safe to re-enter after flooding.",
     5.5, 5.0, None, ["engineering_civil","structural_assessment"], 22.5550, 88.3300, 0.88,
     "New Town Block 2, Rajarhat, Kolkata", "Resident welfare assoc.", "9800776655", 1, "open", False),

    ("nc_048", "food",      "Night emergency - orphanage with 45 children has no food left after flood cut supplies.",
     8.5, 8.3, 45, ["food_distribution","child_care"], 22.5900, 88.4000, 0.91,
     "Shishu Mandir Orphanage, Lake Gardens, Kolkata", "Sister Mary", "9911334455", 1, "open", False),

    ("nc_049", "rescue",    "Old man fell in flood water. Possibly injured. Cannot get up alone. Seen by neighbour.",
     8.0, 7.8, 1, ["search_rescue","medical_first_aid"], 22.5700, 88.3700, 0.80,
     "Near Kalighat Metro, South Kolkata", "Neighbour Bimal", "9877665544", 1, "open", False),

    ("nc_050", "logistics", "Coordination needed for 12 NGOs overlapping relief zones. Resource wastage happening.",
     5.0, 4.8, None, ["logistics_coordination","communications"], 22.5700, 88.3600, 0.95,
     "Central coordination hub, Salt Lake Sector 5", "Coordinator", "9933445566", 1, "open", False),
]

VOLUNTEERS_SEED = [
    # id, name, skills, lat, lng, availability, max_radius_km, total_hours, completed_missions
    ("vol_001", "Arjun Sharma",    ["medical_first_aid","logistics_driver"],                  22.5726, 88.3639, "available", 15, 24.5, 8),
    ("vol_002", "Priya Banerjee",  ["medical_doctor","medical_nurse"],                        22.5800, 88.3500, "available", 20, 48.0, 15),
    ("vol_003", "Rahul Das",       ["search_rescue","logistics_boat_operator"],               22.5600, 88.4100, "busy",      25, 72.0, 22),
    ("vol_004", "Sunita Roy",      ["food_distribution","food_cooking"],                      22.6100, 88.4200, "available", 10, 16.0, 5),
    ("vol_005", "Mohammed Alam",   ["water_purification","water_distribution"],               22.5950, 88.3200, "available", 20, 36.0, 11),
    ("vol_006", "Anita Devi",      ["mental_health_counseling","child_care"],                 22.5400, 88.3700, "offline",   12, 8.0,  3),
    ("vol_007", "Vikram Singh",    ["logistics_driver","logistics_coordination"],             22.5200, 88.2900, "available", 30, 20.0, 7),
    ("vol_008", "Fatima Begum",    ["medical_nurse","elderly_care"],                          22.5500, 88.4000, "available", 15, 40.0, 13),
    ("vol_009", "Raju Mondal",     ["search_rescue","debris_clearance"],                      22.6300, 88.4500, "available", 20, 56.0, 18),
    ("vol_010", "Kavita Joshi",    ["food_distribution","child_care","mental_health_counseling"], 22.5700, 88.3800, "available", 10, 12.0, 4),
    ("vol_011", "Suresh Gupta",    ["logistics_driver","logistics_boat_operator"],            22.5900, 88.3400, "available", 35, 88.0, 28),
    ("vol_012", "Deepa Nair",      ["medical_doctor","medical_paramedic"],                   22.5100, 88.3100, "busy",      20, 60.0, 19),
    ("vol_013", "Amit Ghosh",      ["structural_assessment","engineering_civil"],             22.5750, 88.3900, "available", 25, 32.0, 10),
    ("vol_014", "Rina Chatterjee", ["translation_bengali","food_distribution"],               22.5350, 88.3250, "available", 15, 4.0,  1),
    ("vol_015", "Sanjay Patel",    ["logistics_coordination","communications"],               22.5650, 88.3450, "available", 40, 44.0, 14),
    ("vol_016", "Meera Iyer",      ["translation_tamil","translation_hindi"],                 22.5550, 88.3550, "offline",   10, 0.0,  0),
    ("vol_017", "Arun Kumar",      ["medical_first_aid","search_rescue"],                     22.4900, 88.3200, "available", 20, 28.0, 9),
    ("vol_018", "Pooja Sharma",    ["child_care","mental_health_counseling","food_distribution"], 22.6000, 88.4100, "available", 12, 16.0, 5),
    ("vol_019", "Hassan Khan",     ["debris_clearance","logistics_driver"],                   22.5050, 88.2800, "available", 30, 52.0, 17),
    ("vol_020", "Lakshmi Devi",    ["elderly_care","medical_nurse"],                          22.5400, 88.4100, "available", 15, 36.0, 11),
    ("vol_021", "Biplab Pal",      ["logistics_boat_operator","search_rescue"],               22.6500, 88.4700, "available", 30, 64.0, 20),
    ("vol_022", "Sonia Mukherjee", ["legal_aid","logistics_coordination"],                    22.5900, 88.4300, "offline",   20, 8.0,  2),
    ("vol_023", "Tarun Roy",       ["engineering_electrical","structural_assessment"],        22.5500, 88.3300, "available", 25, 24.0, 7),
    ("vol_024", "Anjali Singh",    ["food_cooking","food_distribution"],                      22.5800, 88.4000, "available", 10, 20.0, 6),
    ("vol_025", "Niloy Bose",      ["medical_paramedic","medical_first_aid"],                 22.5850, 88.3950, "available", 20, 44.0, 14),
    ("vol_026", "Parveen Akhtar",  ["communications","translation_hindi"],                    22.5700, 88.3600, "available", 25, 16.0, 5),
    ("vol_027", "Gita Halder",     ["water_purification","food_distribution"],               22.7400, 88.3800, "available", 15, 32.0, 10),
    ("vol_028", "Debdas Mitra",    ["logistics_driver","logistics_boat_operator","search_rescue"], 22.4500, 88.2400, "available", 50, 96.0, 31),
    ("vol_029", "Kamala Rao",      ["medical_doctor","mental_health_counseling"],             22.5300, 88.3500, "offline",   15, 20.0, 6),
    ("vol_030", "Firoz Ahmed",     ["debris_clearance","structural_assessment","engineering_civil"], 22.5600, 88.3400, "available", 20, 40.0, 12),
]


def _make_needcard(row) -> NeedCard:
    (cid, need_type, desc, ub, ue, affected, skills, lat, lng,
     geo_conf, loc, contact_name, contact_detail, report_count, status, needs_review) = row

    created = datetime.now(timezone.utc) - timedelta(hours=report_count * 2)
    card = NeedCard(
        id=f"seed_{cid}",
        need_type=need_type,
        description_clean=desc,
        urgency_score_base=ub,
        urgency_score_eff=ue,
        urgency_reasoning="Seed data — urgency set manually for demo realism.",
        affected_count=affected,
        skills_needed=skills,
        geo_lat=lat,
        geo_lng=lng,
        geo_confidence=geo_conf,
        location_text_raw=loc,
        contact_name=contact_name,
        contact_detail=contact_detail,
        report_count=report_count,
        status=status,
        needs_review=needs_review,
        created_at=created,
        updated_at=created,
        source_channel="text",
    )
    return card


def _make_volunteer(row) -> Volunteer:
    (vid, name, skills, lat, lng, avail, max_r, hours, missions) = row
    return Volunteer(
        id=f"seed_{vid}",
        name=name,
        skills=skills,
        current_lat=lat,
        current_lng=lng,
        availability=avail,
        max_radius_km=max_r,
        total_hours=hours,
        completed_missions=missions,
        geohash_4="tbd4",   # computed by geo service in production
        geohash_5="tbd55",
    )


async def seed(reset: bool = False):
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    if not project_id:
        print("❌ FIREBASE_PROJECT_ID not set")
        sys.exit(1)

    db = firestore.AsyncClient(project=project_id)

    if reset:
        print("Wiping existing seed data...")
        for cid in [f"seed_nc_{i:03d}" for i in range(1, 51)]:
            await db.collection(COL_NEED_CARDS).document(cid).delete()
        for vid in [f"seed_vol_{i:03d}" for i in range(1, 31)]:
            await db.collection(COL_VOLUNTEERS).document(vid).delete()
        print("Wipe complete.")

    print(f"Seeding {len(NEED_CARDS_SEED)} NeedCards...")
    for row in NEED_CARDS_SEED:
        card = _make_needcard(row)
        await db.collection(COL_NEED_CARDS).document(card.id).set(card.to_firestore())
        print(f"  ✓ {card.id} [{card.need_type}] urgency={card.urgency_score_eff} status={card.status}")

    print(f"\nSeeding {len(VOLUNTEERS_SEED)} Volunteers...")
    for row in VOLUNTEERS_SEED:
        vol = _make_volunteer(row)
        await db.collection(COL_VOLUNTEERS).document(vol.id).set(vol.to_firestore())
        print(f"  ✓ {vol.id} [{vol.name}] avail={vol.availability}")

    print(f"\n✅ Seed complete. {len(NEED_CARDS_SEED)} NeedCards, {len(VOLUNTEERS_SEED)} Volunteers.")
    print("Edge cases: high report_count (nc_010), needs_review (nc_011,025,026,028,040), null geo (nc_011,025).")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Wipe existing seed data first")
    args = parser.parse_args()
    asyncio.run(seed(reset=args.reset))