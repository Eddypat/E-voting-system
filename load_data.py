"""
load_data.py
E-Voting System for Student Elections - Captain Elechi Amadi Polytechnic
--------------------------------------------------------------------------
Loads voters, candidates, and election settings from a human-editable
data.yaml file into the SQLite database, so that an electoral officer can
register a new election's voter register and candidate list without
touching Python or SQL. See Section 4.2.2 and Appendix C.

Usage:
    python load_data.py                 # loads ./data.yaml
    python load_data.py path/to/file.yaml
"""

import sys
import yaml

from database import get_db_connection, init_db, log_event

REQUIRED_STUDENT_FIELDS = {"matric_no", "full_name", "email", "department"}
REQUIRED_CANDIDATE_FIELDS = {"matric_no", "full_name", "position", "department"}


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data:
        raise ValueError("data.yaml is empty or could not be parsed.")
    return data


def validate(data: dict):
    """Fail fast with a clear message rather than a half-populated database."""
    errors = []

    students = data.get("students", [])
    seen_matrics = set()
    for i, s in enumerate(students, start=1):
        missing = REQUIRED_STUDENT_FIELDS - s.keys()
        if missing:
            errors.append(f"students[{i}] is missing field(s): {', '.join(sorted(missing))}")
        matric = s.get("matric_no")
        if matric in seen_matrics:
            errors.append(f"students[{i}] has duplicate matric_no: {matric}")
        seen_matrics.add(matric)

    candidates = data.get("candidates", [])
    for i, c in enumerate(candidates, start=1):
        missing = REQUIRED_CANDIDATE_FIELDS - c.keys()
        if missing:
            errors.append(f"candidates[{i}] is missing field(s): {', '.join(sorted(missing))}")

    if errors:
        raise ValueError("data.yaml failed validation:\n  - " + "\n  - ".join(errors))


def load_into_db(data: dict, reset: bool = True):
    # seed_samples=False: this file's own students/candidates replace the
    # built-in demo data rather than being mixed in alongside it.
    init_db(reset=reset, seed_samples=False)
    conn = get_db_connection()

    election = data.get("election", {})
    if election:
        conn.execute(
            "UPDATE election_settings SET election_name = ?, is_active = ? WHERE setting_id = "
            "(SELECT setting_id FROM election_settings ORDER BY setting_id DESC LIMIT 1)",
            (election.get("name", "Student Union Government Election"), int(bool(election.get("is_active", True)))),
        )

    students = data.get("students", [])
    for s in students:
        conn.execute(
            """INSERT OR IGNORE INTO students (matric_no, full_name, email, department)
               VALUES (?, ?, ?, ?)""",
            (s["matric_no"].strip().upper(), s["full_name"], s["email"], s["department"]),
        )

    candidates = data.get("candidates", [])
    for c in candidates:
        conn.execute(
            """INSERT INTO candidates (matric_no, full_name, position, department, photo, manifesto)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (c["matric_no"], c["full_name"], c["position"], c["department"],
             c.get("photo"), c.get("manifesto", "")),
        )

    conn.commit()
    conn.close()
    log_event("DATA_LOADED", f"{len(students)} students and {len(candidates)} candidates loaded from YAML")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data.yaml"
    print(f"Loading election data from {path} ...")
    data = load_yaml(path)
    validate(data)
    load_into_db(data, reset=True)
    print(f"Done: {len(data.get('students', []))} students and "
          f"{len(data.get('candidates', []))} candidates loaded.")
    print("Election:", data.get("election", {}).get("name", "(unnamed)"))


if __name__ == "__main__":
    main()
