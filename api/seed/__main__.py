"""Seed the database: the pack's starter data plus generated volume.

    python -m seed                      # 100,000 patients / 400,000 visits (the Section B volumes)
    python -m seed --patients 2000 --visits 8000

Deterministic (fixed random seed), so every reviewer gets the same numbers. Generated dates are
relative to "today" (AS_OF_DATE, or the real date in Africa/Lusaka). Rows are loaded with COPY.
Everything is invented; names are drawn from short lists of common Zambian names.
"""
import argparse
import io
import json
import random
import time
import uuid
from datetime import UTC, date, datetime, time as dtime, timedelta
from pathlib import Path

import psycopg

from app.config import get_settings

RNG_SEED = 20261006
SAMPLE = json.loads((Path(__file__).parent / "sample_data.json").read_text())

EXTRA_FACILITIES = [
    ("FAC-0102", "Mwansa Central Clinic", "Mwansa"),
    ("FAC-0103", "Kasompe Health Post", "Mwansa"),
    ("FAC-0104", "Nkana East Clinic", "Mwansa"),
    ("FAC-0208", "Mutende Rural Health Centre", "Kalemba"),
    ("FAC-0209", "Chisanga Health Post", "Kalemba"),
    ("FAC-0210", "Kalemba Mission Hospital", "Kalemba"),
    ("FAC-0313", "Chembe Urban Clinic", "Chembe"),
    ("FAC-0314", "Lubwe Rural Health Centre", "Chembe"),
    ("FAC-0315", "Mansa Road Clinic", "Chembe"),
]
# Share of generated patients per facility. FAC-0101 is large enough that its follow-up list
# holds over 10,000 patients, the size the brief asks the screen to handle.
WEIGHTS = {"FAC-0101": 35, "FAC-0312": 15, "FAC-0207": 8}
OTHER_WEIGHT = (100 - sum(WEIGHTS.values())) / len(EXTRA_FACILITIES)

FIRST_F = ["Thandiwe", "Chipo", "Mwila", "Natasha", "Bupe", "Chilufya", "Mutinta", "Namakau", "Lweendo",
           "Mapalo", "Taonga", "Chisomo", "Musonda", "Inonge", "Kasuba", "Mwaka", "Nchimunya", "Precious",
           "Ruth", "Grace", "Esther", "Mercy", "Joyce", "Memory", "Agness", "Febby", "Loveness", "Beatrice"]
FIRST_M = ["Mulenga", "Chanda", "Bwalya", "Mwansa", "Kondwani", "Mutale", "Chileshe", "Lubinda", "Mapalo",
           "Kelvin", "Brian", "Joseph", "Emmanuel", "Moses", "Daniel", "Kennedy", "Patrick", "Gift",
           "Charles", "Mubanga", "Kabwe", "Chibwe", "Nkandu", "Sitali", "Mwiinga", "Hamoonga"]
LAST = ["Banda", "Phiri", "Zulu", "Mwale", "Tembo", "Mumba", "Chanda", "Mulenga", "Bwalya", "Lungu",
        "Sakala", "Daka", "Ngoma", "Mbewe", "Kabwe", "Musonda", "Chilufya", "Kunda", "Mwila", "Nyirenda",
        "Simwanza", "Hamoonga", "Mudenda", "Sichone", "Kaunda", "Chisenga", "Mutale", "Kapembwa",
        "Siame", "Nkhata", "Zimba", "Chirwa", "Moono", "Hichilema", "Siakavuba", "Mwanza"]

# Where each patient's most recent appointment sits relative to today (days past, so negative is
# ahead), and how often. Calibrated so ~30% of patients are on the default list.
OUTCOMES = [
    ("overdue",        23, (15, 400)),
    ("missed",          7, (8, 14)),
    ("grace",           4, (1, 7)),
    ("due_soon",        6, (-7, 0)),
    ("future",         45, (-120, -8)),
    ("no_appointment", 15, None),
]


def _visits_per_patient(rng: random.Random, n_patients: int, n_visits: int) -> list[int]:
    """1 to 7 visits each, summing exactly to n_visits."""
    counts = [1] * n_patients
    remaining = n_visits - n_patients
    while remaining > 0:
        i = rng.randrange(n_patients)
        if counts[i] < 7:
            counts[i] += 1
            remaining -= 1
    return counts


def _ts(d: date, rng: random.Random) -> datetime:
    return datetime.combine(d, dtime(rng.randint(6, 16), rng.randint(0, 59)), tzinfo=UTC)


def generate(today: date, n_patients: int, n_visits: int):
    rng = random.Random(RNG_SEED)
    facility_ids = [f for f in WEIGHTS] + [f for f, _, _ in EXTRA_FACILITIES]
    weights = [WEIGHTS.get(f, OTHER_WEIGHT) for f in facility_ids]
    taken = {(p["facility_id"], p["patient_number"]) for p in SAMPLE["patients"]}
    next_number = {f: 1000 for f in facility_ids}
    outcome_names = [o[0] for o in OUTCOMES]
    outcome_weights = [o[1] for o in OUTCOMES]
    outcome_ranges = {o[0]: o[2] for o in OUTCOMES}

    patients, visits, contacts = [], [], []
    for n_visit in _visits_per_patient(rng, n_patients, n_visits):
        fac = rng.choices(facility_ids, weights)[0]
        while (fac, number := f"{fac[4:]}-{next_number[fac]:06d}") in taken:
            next_number[fac] += 1
        next_number[fac] += 1
        sex = rng.choices(["female", "male", "other"], [52, 47, 1])[0]
        first = rng.choice(FIRST_F if sex == "female" else FIRST_M if sex == "male" else FIRST_F + FIRST_M)
        pid = uuid.UUID(int=rng.getrandbits(128), version=4)
        dob = today - timedelta(days=rng.randint(365, 80 * 365))
        phone = None if rng.random() < 0.2 else f"+2609{rng.choice('567')}{rng.randint(0, 9_999_999):07d}"

        # Build the visit chain backwards from the most recent visit.
        outcome = rng.choices(outcome_names, outcome_weights)[0]
        rng_days = outcome_ranges[outcome]
        if rng_days is None:  # most recent visit set no next appointment
            last_visit = today - timedelta(days=rng.randint(0, 300))
            last_appt = None
        else:
            appt = today - timedelta(days=rng.randint(*rng_days))
            interval = rng.randint(14, 91)
            last_visit = min(appt - timedelta(days=interval), today)
            last_appt = appt
        chain = [(last_visit, last_appt)]
        cursor = last_visit
        for _ in range(n_visit - 1):
            gap = rng.randint(21, 120)
            prev_visit = cursor - timedelta(days=gap)
            # Earlier visits usually booked the next one; some patients came early or late.
            prev_appt = prev_visit + timedelta(days=max(0, gap + rng.randint(-10, 10)))
            chain.append((prev_visit, max(prev_appt, prev_visit)))
            cursor = prev_visit
        first_visit = chain[-1][0]
        patients.append((pid, fac, number, first, rng.choice(LAST), dob, sex, phone,
                         _ts(first_visit - timedelta(days=rng.randint(0, 3)), rng)))
        for i, (vd, na) in enumerate(chain):
            vtype = "routine" if i == len(chain) - 1 else rng.choice(["routine", "follow_up", "follow_up"])
            if na is None:
                vtype = "unscheduled"
            visits.append((uuid.UUID(int=rng.getrandbits(128), version=4), pid, vd, na, vtype, _ts(vd, rng)))

        if outcome in ("overdue", "missed") and rng.random() < 0.25 and last_appt is not None:
            when = last_appt + timedelta(days=rng.randint(1, max(1, (today - last_appt).days)))
            contacts.append((pid, fac, _ts(min(when, today), rng), None, "seed", "0" * 64))
    return patients, visits, contacts


def _copy(cur: psycopg.Cursor, table: str, columns: list[str], rows: list[tuple]) -> None:
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--patients", type=int, default=100_000, help="total patients, including the sample")
    parser.add_argument("--visits", type=int, default=400_000, help="total visits, including the sample")
    args = parser.parse_args()

    settings = get_settings()
    today = settings.today()
    started = time.perf_counter()
    n_gen_patients = args.patients - len(SAMPLE["patients"])
    n_gen_visits = args.visits - len(SAMPLE["visits"])
    if n_gen_patients < 0 or n_gen_visits < n_gen_patients:
        raise SystemExit("need visits >= patients >= the 3 sample patients")
    patients, visits, contacts = generate(today, n_gen_patients, n_gen_visits)
    print(f"generated {len(patients):,} patients and {len(visits):,} visits "
          f"(as of {today}) in {time.perf_counter() - started:.1f}s")

    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE contact_attempt, visit, patient, facility")
        facilities = [(f["facility_id"], f["name"], f["district"]) for f in SAMPLE["facilities"]]
        _copy(cur, "facility", ["facility_id", "name", "district"], facilities + EXTRA_FACILITIES)

        # Sample data from the pack, with fixed dates exactly as given.
        ids: dict[str, uuid.UUID] = {}
        for p in SAMPLE["patients"]:
            cur.execute("""INSERT INTO patient (facility_id, patient_number, first_name, last_name,
                                                date_of_birth, sex, phone_number, created_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, '2026-06-01T08:00:00Z') RETURNING id""",
                        (p["facility_id"], p["patient_number"], p["first_name"], p["last_name"],
                         p["date_of_birth"], p["sex"], p["phone_number"]))
            ids[p["patient_number"]] = cur.fetchone()[0]  # type: ignore[index]
        for v in SAMPLE["visits"]:
            cur.execute("""INSERT INTO visit (patient_id, visit_date, next_appointment_date, visit_type, created_at)
                           VALUES (%s, %s, %s, %s, (%s::date + time '10:00') AT TIME ZONE 'Africa/Lusaka')""",
                        (ids[v["patient_number"]], v["visit_date"], v["next_appointment_date"],
                         v["visit_type"], v["visit_date"]))
        for c in SAMPLE["contact_attempts"]:
            cur.execute("""INSERT INTO contact_attempt (patient_id, facility_id, contacted_at, note,
                                                        recorded_by, request_hash)
                           SELECT id, facility_id, %s, %s, %s, repeat('0', 64) FROM patient WHERE id = %s""",
                        (c["contacted_at"], c["note"], c["recorded_by"], ids[c["patient_number"]]))

        _copy(cur, "patient", ["id", "facility_id", "patient_number", "first_name", "last_name",
                               "date_of_birth", "sex", "phone_number", "created_at"], patients)
        _copy(cur, "visit", ["id", "patient_id", "visit_date", "next_appointment_date", "visit_type",
                             "created_at"], visits)
        _copy(cur, "contact_attempt", ["patient_id", "facility_id", "contacted_at", "note", "recorded_by",
                                       "request_hash"], contacts)
        conn.commit()

    # Fresh statistics and visibility map, so the planner uses index-only scans straight away.
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("VACUUM ANALYZE")
        counts = conn.execute("""SELECT (SELECT count(*) FROM patient), (SELECT count(*) FROM visit),
                                        (SELECT count(*) FROM contact_attempt)""").fetchone()
    print(f"loaded {counts[0]:,} patients, {counts[1]:,} visits, {counts[2]:,} contact attempts "  # type: ignore[index]
          f"in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
