"""
scripts/generate_dataset.py
============================
Generates the synthetic "Operation Nexus" investigation dataset used by the
SIH PS-189 prototype.

IMPORTANT: All data below is entirely fictional. No real people, phone
numbers, vehicles, or locations are represented. This script produces a
JSON dataset that is loaded into the application's SQLite database at
startup by backend/app/seed.py.

Design goals for the synthetic data (per project brief):
  - Contains aliases / spelling variants of the same real-world identity
    (for entity resolution to discover).
  - Contains a deliberately UNRECORDED (hidden) relationship between two
    people who are only connected through an indirect evidence chain
    (phone -> person -> vehicle -> location), for the hidden-link
    detection feature to surface as a "potential lead".
  - Every relationship is backed by at least one synthetic evidence
    record (call log, sighting, financial record, etc.) so the app can
    demonstrate evidence-aware provenance.
  - Relationships carry timestamps so the app can demonstrate temporal
    filtering.
  - A ground-truth section records which entities are "actually" the
    same person and which hidden link is "actually" real, for internal
    evaluation only. This is NEVER exposed directly in the UI.

Run:
    python3 generate_dataset.py > ../data/operation_nexus.json
"""

import json
import random
from datetime import datetime, timedelta

random.seed(42)

FIRST_NAMES = [
    "Arjun", "Vikram", "Rohan", "Karan", "Aditya", "Nikhil", "Sanjay", "Rahul",
    "Anil", "Suresh", "Manoj", "Deepak", "Ravi", "Ajay", "Vivek", "Amit",
    "Priya", "Neha", "Kavita", "Sunita", "Anjali", "Pooja", "Meera", "Divya",
    "Rekha", "Shalini", "Nisha", "Ritu", "Farhan", "Imran", "Salim", "Yusuf",
    "Harpreet", "Gurpreet", "Baljeet", "Manpreet", "Tara", "Isha", "Aisha",
    "Zara", "Om", "Siddharth", "Kunal", "Varun", "Rajesh", "Mahesh", "Naresh",
    "Dinesh", "Yogesh", "Prakash",
]
LAST_NAMES = [
    "Kumar", "Sharma", "Verma", "Singh", "Gupta", "Yadav", "Mishra", "Chauhan",
    "Rathore", "Bhatt", "Joshi", "Nair", "Menon", "Reddy", "Naidu", "Iyer",
    "Malhotra", "Kapoor", "Chopra", "Bhatia", "Saxena", "Tiwari", "Pandey",
    "Dubey", "Khan", "Ansari", "Sheikh", "Qureshi", "Dhillon", "Sandhu",
]
ORG_ADJ = ["Nexus", "Silverline", "Coastal", "Metro", "United", "Everest",
           "Blue Ridge", "Sunrise", "Delta", "Continental", "Prime"]
ORG_NOUN = ["Traders", "Logistics", "Holdings", "Imports", "Freight",
            "Enterprises", "Ventures", "Shipping", "Textiles", "Motors"]
CITIES = [
    ("Kranti Nagar Transit Yard", 28.61, 77.20), ("Old Harbor Warehouse District", 19.05, 72.85),
    ("Riverside Industrial Estate", 22.57, 88.35), ("Highway 7 Rest Stop", 12.97, 77.59),
    ("Central Bus Terminal", 26.85, 80.94), ("Lakeview Business Park", 17.38, 78.48),
    ("North Ring Road Depot", 30.73, 76.78), ("Sundar Vihar Apartments", 28.65, 77.10),
    ("Eastside Freight Yard", 22.72, 88.42), ("Palm Grove Farmhouse", 12.92, 77.62),
    ("Green Valley Guest House", 30.35, 76.36), ("Silver Sands Motel", 15.30, 73.83),
    ("Junction Road Tea Stall", 25.32, 82.99), ("Marina Drive Parking Lot", 13.05, 80.28),
    ("Foothill Storage Units", 30.90, 75.85),
]
VEHICLE_MAKES = ["Maruti Swift", "Hyundai i20", "Tata Ace", "Mahindra Bolero",
                  "Toyota Innova", "Honda City", "Royal Enfield Classic",
                  "Ashok Leyland Truck", "Bajaj Pulsar", "Force Traveller"]
EVENT_TYPES = ["Vehicle sighting", "Money transfer flagged", "SIM registered",
               "Border checkpoint log", "Warehouse entry log", "Informant tip",
               "CCTV capture", "Toll booth record"]

def rand_date(start, end):
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))

START = datetime(2026, 8, 1)
END = datetime(2026, 8, 28)

def gen_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

def gen_phone():
    return f"+91-{random.choice(['70','81','90','98','99'])}{random.randint(10000000,99999999)}"

def gen_org():
    return f"{random.choice(ORG_ADJ)} {random.choice(ORG_NOUN)}"

def gen_vehicle():
    plate = f"{random.choice(['DL','MH','WB','KA','PB','UP','GJ'])}-{random.randint(10,99)}-{random.choice('ABCDEFGHJK')}{random.choice('ABCDEFGHJK')}-{random.randint(1000,9999)}"
    return random.choice(VEHICLE_MAKES), plate

persons = []
phones = []
vehicles = []
locations = []
organizations = []
events = []
evidence = []
relationships = []
cases = []

def new_id(prefix, n):
    return f"{prefix}_{n:04d}"

ev_counter = [0]
def add_evidence(ev_type, description, source_record, ts, confidence=1.0):
    ev_counter[0] += 1
    eid = new_id("EVD", ev_counter[0])
    evidence.append({
        "id": eid,
        "type": ev_type,
        "description": description,
        "source_record": source_record,
        "timestamp": ts.isoformat(),
        "extraction_confidence": round(confidence, 2),
    })
    return eid

rel_counter = [0]
def add_relationship(src, dst, rtype, ts=None, confidence=1.0, status="observed",
                      evidence_ids=None, notes=""):
    rel_counter[0] += 1
    rid = new_id("REL", rel_counter[0])
    relationships.append({
        "id": rid,
        "source": src,
        "target": dst,
        "type": rtype,
        "timestamp": ts.isoformat() if ts else None,
        "confidence": round(confidence, 2),
        "status": status,  # observed | inferred | possible_same_as | possible_link
        "evidence_ids": evidence_ids or [],
        "notes": notes,
    })
    return rid

# ---------------------------------------------------------------------------
# 1. Cases
# ---------------------------------------------------------------------------
cases.append({
    "id": "CASE_001",
    "name": "Operation Nexus - Phase I",
    "type": "Organized smuggling network",
    "status": "Active",
    "period_start": "2026-08-01",
    "period_end": "2026-08-28",
    "description": "Investigation into a suspected contraband distribution "
                   "network operating across four states, initiated after "
                   "a flagged shipment at a highway checkpoint.",
})
cases.append({
    "id": "CASE_002",
    "name": "Operation Nexus - Phase II (Financial Trail)",
    "type": "Financial fraud / money mule network",
    "status": "Active",
    "period_start": "2026-08-05",
    "period_end": "2026-08-28",
    "description": "Parallel investigation into suspicious financial "
                   "transfers suspected of laundering proceeds connected "
                   "to Phase I, opened by a different investigating unit.",
})

# ---------------------------------------------------------------------------
# 2. Core cast — deliberately designed cluster (hand-authored for the demo)
# ---------------------------------------------------------------------------
# Person P0001 "Rajesh Kumar" is the central figure of CASE_001.
# He has an ALIAS record P0002 "R. Kumar / Raju" that entity resolution
# should suggest merging (same phone, same vehicle, overlapping locations,
# but a contradicting reported age) -- the flagship "possible same as" demo.
#
# Person P0050 "Meera Fernandes" is the central figure of CASE_002.
# She has NO recorded direct link to Rajesh Kumar. But there IS a hidden
# evidence chain:
#   Rajesh Kumar --(used_phone)--> Phone PH0001
#   Phone PH0001 --(contacted)--> Person P0030 "Salim Ansari"
#   Salim Ansari --(used_vehicle)--> Vehicle VH0010
#   Vehicle VH0010 --(sighted_at)--> Location LOC0005 "Riverside Industrial Estate"
#   Meera Fernandes --(sighted_at)--> Location LOC0005 "Riverside Industrial Estate"
# None of these individual facts directly link Rajesh <-> Meera, but the
# hidden-link detector should surface this as a candidate investigative lead.

persons.append({"id": "P0001", "name": "Rajesh Kumar", "aliases": [],
                 "reported_age": 34, "nationality": "Indian",
                 "notes": "Primary subject, Case 001. Runs a small transport "
                          "brokerage as a front business."})
persons.append({"id": "P0002", "name": "R. Kumar", "aliases": ["Raju"],
                 "reported_age": 29, "nationality": "Indian",
                 "notes": "Appears in an informant tip and a toll record; "
                          "identity not yet confirmed to be Rajesh Kumar."})
persons.append({"id": "P0030", "name": "Salim Ansari", "aliases": ["Sallu"],
                 "reported_age": 41, "nationality": "Indian",
                 "notes": "Frequent contact of Phone PH0001. Suspected "
                          "logistics coordinator."})
persons.append({"id": "P0050", "name": "Meera Fernandes", "aliases": [],
                 "reported_age": 38, "nationality": "Indian",
                 "notes": "Primary subject, Case 002. Manages accounts for "
                          "Silverline Holdings."})

phones.append({"id": "PH0001", "number": gen_phone(), "carrier": "Airnet Mobile",
               "registered_owner": "Unregistered / prepaid"})
vehicles.append({"id": "VH0010", "make": "Tata Ace", "plate": "DL-14-BK-7731"})
locations.append({"id": "LOC0005", "name": "Riverside Industrial Estate",
                   "lat": 22.57, "lng": 88.35, "location_type": "Industrial estate"})
organizations.append({"id": "ORG0003", "name": "Silverline Holdings",
                       "org_type": "Financial services (shell suspected)"})

# Wire up the designed cluster with evidence
t1 = datetime(2026, 8, 3, 14, 20)
eid = add_evidence("Communication Record", "SIM PH0001 registered to a device "
                    "later linked to Rajesh Kumar via a shared recharge outlet.",
                    "SIM_REG_004", t1, 0.81)
add_relationship("P0001", "PH0001", "USED_PHONE", t1, 0.81, "observed", [eid])

t2 = datetime(2026, 8, 4, 9, 12)
eid = add_evidence("Call Log", "42 outgoing calls from PH0001 to Salim Ansari's "
                    "registered number between Aug 2-15.", "CALL_LOG_018", t2, 0.94)
add_relationship("PH0001", "P0030", "CONTACTED", t2, 0.94, "observed", [eid])

t3 = datetime(2026, 8, 6, 18, 45)
eid = add_evidence("Vehicle Registration", "Vehicle VH0010 registered under a "
                    "transport permit co-signed by Salim Ansari.", "VEH_REG_010", t3, 0.9)
add_relationship("P0030", "VH0010", "USED_VEHICLE", t3, 0.9, "observed", [eid])

t4 = datetime(2026, 8, 9, 22, 5)
eid = add_evidence("CCTV Capture", "ANPR camera logged VH0010 entering Riverside "
                    "Industrial Estate at night, no recorded business there.",
                    "CCTV_CAP_027", t4, 0.88)
add_relationship("VH0010", "LOC0005", "LOCATED_AT", t4, 0.88, "observed", [eid])

t5 = datetime(2026, 8, 12, 11, 30)
eid = add_evidence("Financial Record", "Bank teller statement places Meera "
                    "Fernandes at a Riverside Industrial Estate ATM withdrawing "
                    "cash for an unlisted vendor payment.", "BANK_STMT_055", t5, 0.85)
add_relationship("P0050", "LOC0005", "LOCATED_AT", t5, 0.85, "observed", [eid])

# The alias / duplicate-identity pair: give P0002 overlapping signals with P0001
t6 = datetime(2026, 8, 2, 8, 0)
eid = add_evidence("Toll Booth Record", "Toll camera log shows driver matching "
                    "'R. Kumar' description using vehicle VH0010 near Case 001 "
                    "corridor.", "TOLL_LOG_003", t6, 0.7)
add_relationship("P0002", "VH0010", "USED_VEHICLE", t6, 0.7, "observed", [eid])

t7 = datetime(2026, 8, 3, 15, 0)
eid = add_evidence("Communication Record", "Same PH0001 device briefly used a "
                    "second SIM slot registered under the alias 'Raju'.",
                    "SIM_REG_005", t7, 0.66)
add_relationship("P0002", "PH0001", "USED_PHONE", t7, 0.66, "observed", [eid])

t8 = datetime(2026, 8, 5, 19, 0)
eid = add_evidence("Informant Tip", "Field informant reports 'R. Kumar aka Raju' "
                    "and 'Rajesh Kumar' were seen together only once, described "
                    "as if the same person by two separate witnesses on "
                    "different days.", "INFORMANT_TIP_009", t8, 0.55)
# This is the possible_same_as suggestion the entity-resolution screen will show
add_relationship("P0001", "P0002", "POSSIBLE_SAME_AS", t8, 0.87, "inferred", [eid],
                  notes="Entity resolution: name similarity + shared phone + "
                        "shared vehicle, contradicted by reported age gap (34 vs 29).")

# Case membership
add_relationship("P0001", "CASE_001", "INVOLVED_IN", t1, 1.0, "observed", [])
add_relationship("P0002", "CASE_001", "INVOLVED_IN", t6, 1.0, "observed", [])
add_relationship("P0030", "CASE_001", "INVOLVED_IN", t2, 1.0, "observed", [])
add_relationship("P0050", "CASE_002", "INVOLVED_IN", t5, 1.0, "observed", [])
add_relationship("P0050", "ORG0003", "MEMBER_OF", t5, 0.92, "observed", [])

GROUND_TRUTH = {
    "same_entity_pairs": [["P0001", "P0002"]],
    "hidden_real_links": [["P0001", "P0050"]],
    "note": "Internal evaluation data only. Not exposed in the application UI.",
}

# ---------------------------------------------------------------------------
# 3. Bulk-generate the surrounding network for scale + realistic analytics
# ---------------------------------------------------------------------------
N_EXTRA_PERSONS = 90
N_PHONES = 55
N_VEHICLES = 45
N_LOCATIONS = 15 - 1  # LOC0005 already created
N_ORGS = 18

used_ids = {p["id"] for p in persons}
for i in range(2, N_EXTRA_PERSONS + 3):
    pid = new_id("P", i * 10)
    if pid in used_ids:
        continue
    persons.append({
        "id": pid, "name": gen_name(),
        "aliases": [], "reported_age": random.randint(19, 62),
        "nationality": "Indian", "notes": "",
    })

for i in range(2, N_PHONES + 2):
    phid = new_id("PH", i)
    phones.append({"id": phid, "number": gen_phone(),
                    "carrier": random.choice(["Airnet Mobile", "Jio-Sim Co",
                                               "Vodaphone Circle", "BSNL Grid"]),
                    "registered_owner": random.choice(["Unregistered / prepaid",
                                                        gen_name()])})

for i in range(2, N_VEHICLES + 2):
    vid = new_id("VH", i)
    make, plate = gen_vehicle()
    vehicles.append({"id": vid, "make": make, "plate": plate})

for i, (name, lat, lng) in enumerate(CITIES[1:N_LOCATIONS + 1], start=2):
    locations.append({"id": new_id("LOC", i), "name": name, "lat": lat, "lng": lng,
                       "location_type": random.choice(["Warehouse", "Residential",
                                                        "Transit hub", "Commercial",
                                                        "Rural / remote"])})

for i in range(2, N_ORGS + 2):
    organizations.append({"id": new_id("ORG", i), "name": gen_org(),
                           "org_type": random.choice(["Logistics", "Trading company",
                                                        "Financial services",
                                                        "Shell company (suspected)",
                                                        "Transport union"])})

# Random background relationships to make the graph rich & analyzable
all_person_ids = [p["id"] for p in persons]
all_phone_ids = [p["id"] for p in phones]
all_vehicle_ids = [v["id"] for v in vehicles]
all_loc_ids = [l["id"] for l in locations]
all_org_ids = [o["id"] for o in organizations]
all_case_ids = [c["id"] for c in cases]

REL_TEMPLATES_PERSON_PERSON = ["CONTACTED", "MET", "ASSOCIATED_WITH"]

for _ in range(260):
    a, b = random.sample(all_person_ids, 2)
    ts = rand_date(START, END)
    rtype = random.choice(REL_TEMPLATES_PERSON_PERSON)
    conf = round(random.uniform(0.55, 0.98), 2)
    ev_type = random.choice(["Call Log", "CCTV Capture", "Informant Tip",
                              "Surveillance Report", "Financial Record"])
    eid = add_evidence(ev_type, f"{ev_type} indicates a {rtype.lower()} event "
                        f"between the two subjects.", f"AUTO_{ev_type[:4].upper()}_"
                        f"{random.randint(1000,9999)}", ts, conf)
    add_relationship(a, b, rtype, ts, conf, "observed", [eid])

for _ in range(70):
    p = random.choice(all_person_ids)
    ph = random.choice(all_phone_ids)
    ts = rand_date(START, END)
    eid = add_evidence("Communication Record", "SIM registration / usage record "
                        "links subject to device.", f"SIM_REG_{random.randint(100,999)}",
                        ts, round(random.uniform(0.6, 0.97), 2))
    add_relationship(p, ph, "USED_PHONE", ts, round(random.uniform(0.6, 0.97), 2),
                      "observed", [eid])

for _ in range(60):
    p = random.choice(all_person_ids)
    v = random.choice(all_vehicle_ids)
    ts = rand_date(START, END)
    eid = add_evidence("Vehicle Registration", "Ownership/usage permit or "
                        "checkpoint log links subject to vehicle.",
                        f"VEH_REG_{random.randint(100,999)}", ts,
                        round(random.uniform(0.6, 0.95), 2))
    add_relationship(p, v, "USED_VEHICLE", ts, round(random.uniform(0.6, 0.95), 2),
                      "observed", [eid])

for _ in range(90):
    v = random.choice(all_vehicle_ids)
    l = random.choice(all_loc_ids)
    ts = rand_date(START, END)
    eid = add_evidence("CCTV Capture", "ANPR / CCTV log places vehicle at "
                        "location.", f"CCTV_CAP_{random.randint(100,999)}", ts,
                        round(random.uniform(0.65, 0.95), 2))
    add_relationship(v, l, "LOCATED_AT", ts, round(random.uniform(0.65, 0.95), 2),
                      "observed", [eid])

for _ in range(70):
    p = random.choice(all_person_ids)
    l = random.choice(all_loc_ids)
    ts = rand_date(START, END)
    eid = add_evidence("Surveillance Report", "Field surveillance places "
                        "subject at location.", f"SURV_{random.randint(100,999)}",
                        ts, round(random.uniform(0.6, 0.93), 2))
    add_relationship(p, l, "LOCATED_AT", ts, round(random.uniform(0.6, 0.93), 2),
                      "observed", [eid])

for _ in range(40):
    p = random.choice(all_person_ids)
    o = random.choice(all_org_ids)
    ts = rand_date(START, END)
    eid = add_evidence("Corporate Record", "Registrar filing or employment "
                        "record links subject to organization.",
                        f"CORP_REC_{random.randint(100,999)}", ts,
                        round(random.uniform(0.7, 0.96), 2))
    add_relationship(p, o, random.choice(["MEMBER_OF", "ASSOCIATED_WITH"]), ts,
                      round(random.uniform(0.7, 0.96), 2), "observed", [eid])

for pid in all_person_ids:
    if random.random() < 0.55:
        ts = rand_date(START, END)
        add_relationship(pid, random.choice(all_case_ids), "INVOLVED_IN", ts, 1.0,
                          "observed", [])

# A handful of timestamped "events" for the timeline feature
event_counter = 0
for _ in range(30):
    event_counter += 1
    ts = rand_date(START, END)
    events.append({
        "id": new_id("EVT", event_counter),
        "type": random.choice(EVENT_TYPES),
        "timestamp": ts.isoformat(),
        "location_id": random.choice(all_loc_ids),
        "description": f"{random.choice(EVENT_TYPES)} logged during active "
                        f"surveillance window.",
        "case_id": random.choice(all_case_ids),
    })

# A few extra un-reviewed "possible_same_as" entity-resolution candidates
# beyond the flagship P0001/P0002 pair, generated by simple name-similarity.
def name_key(n):
    return n.lower().replace(".", "").split()[-1]

seen_by_lastname = {}
for p in persons:
    seen_by_lastname.setdefault(name_key(p["name"]), []).append(p["id"])

extra_pairs_added = 0
for lastname, ids in seen_by_lastname.items():
    if len(ids) >= 2 and extra_pairs_added < 6:
        a, b = ids[0], ids[1]
        if a == "P0001" or b == "P0001":
            continue
        ts = rand_date(START, END)
        eid = add_evidence("Name Matching", f"Automated name-similarity scan "
                            f"flagged two records sharing surname '{lastname}' "
                            f"with overlapping location history.",
                            f"NAME_MATCH_{random.randint(100,999)}", ts, 0.6)
        add_relationship(a, b, "POSSIBLE_SAME_AS", ts,
                          round(random.uniform(0.45, 0.75), 2), "inferred", [eid],
                          notes="Automated candidate: surname match + partial "
                                "location overlap. Needs investigator review.")
        extra_pairs_added += 1

dataset = {
    "meta": {
        "name": "Operation Nexus",
        "description": "Synthetic demonstration dataset for SIH 2026 PS-189. "
                        "No real individuals, organizations, vehicles, or "
                        "locations are represented.",
        "generated_at": datetime.now().isoformat(),
    },
    "cases": cases,
    "persons": persons,
    "phones": phones,
    "vehicles": vehicles,
    "locations": locations,
    "organizations": organizations,
    "events": events,
    "evidence": evidence,
    "relationships": relationships,
    "ground_truth": GROUND_TRUTH,
}

print(json.dumps(dataset, indent=2))
