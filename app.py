"""
app.py
E-Voting System for Student Elections - Captain Elechi Amadi Polytechnic
--------------------------------------------------------------------------
Main Flask application. Implements voter authentication (matric no. + OTP),
ballot casting, real-time result tallying, and the admin module.

Author : Nwaobasi Mercy Chinenye (CEAP/N-COM/2024/3226)
"""

import os
import random
import hashlib
import secrets
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, session, flash

from database import get_db_connection, init_db, log_event, hash_password

app = Flask(__name__)
# In production (e.g. on Render), set a fixed SECRET_KEY environment variable
# so that sessions survive a server restart instead of all being invalidated.
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(16))

DEMO_MODE = os.environ.get("DEMO_MODE", "1") != "0"


@app.route("/")
def index():
    conn = get_db_connection()
    election = conn.execute("SELECT * FROM election_settings ORDER BY setting_id DESC LIMIT 1").fetchone()
    conn.close()
    return render_template("index.html", election=election)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        matric_no = request.form.get("matric_no", "").strip().upper()
        conn = get_db_connection()
        student = conn.execute(
            "SELECT * FROM students WHERE matric_no = ?", (matric_no,)
        ).fetchone()

        if not student:
            flash("Matriculation number not found in the voters' register.", "error")
            conn.close()
            return redirect(url_for("login"))

        if student["has_voted"]:
            flash("Our records show you have already cast your vote in this election.", "error")
            conn.close()
            log_event("DUPLICATE_LOGIN_ATTEMPT", f"Matric {matric_no} attempted repeat login")
            return redirect(url_for("login"))

        otp = f"{random.randint(100000, 999999)}"
        otp_hash = hashlib.sha256(otp.encode()).hexdigest()
        expiry = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

        conn.execute(
            "UPDATE students SET otp_code = ?, otp_expiry = ? WHERE matric_no = ?",
            (otp_hash, expiry, matric_no),
        )
        conn.commit()
        conn.close()

        session["pending_matric"] = matric_no
        log_event("OTP_ISSUED", f"OTP issued to {matric_no}")

        demo_otp = otp if DEMO_MODE else None
        return render_template("otp.html", matric_no=matric_no, demo_otp=demo_otp)

    return render_template("login.html")


@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    matric_no = session.get("pending_matric")
    entered_otp = request.form.get("otp", "").strip()

    if not matric_no:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    student = conn.execute("SELECT * FROM students WHERE matric_no = ?", (matric_no,)).fetchone()

    if not student or not student["otp_code"]:
        conn.close()
        flash("Invalid session. Please try again.", "error")
        return redirect(url_for("login"))

    if datetime.now() > datetime.strptime(student["otp_expiry"], "%Y-%m-%d %H:%M:%S"):
        conn.close()
        flash("Your OTP has expired. Please request a new one.", "error")
        log_event("OTP_EXPIRED", f"Expired OTP attempt by {matric_no}")
        return redirect(url_for("login"))

    entered_hash = hashlib.sha256(entered_otp.encode()).hexdigest()
    if entered_hash != student["otp_code"]:
        conn.close()
        flash("Incorrect OTP. Please try again.", "error")
        log_event("OTP_MISMATCH", f"Wrong OTP attempt by {matric_no}")
        return render_template("otp.html", matric_no=matric_no, demo_otp=None, error=True)

    conn.execute(
        "UPDATE students SET otp_code = NULL, otp_expiry = NULL WHERE matric_no = ?",
        (matric_no,),
    )
    conn.commit()
    conn.close()

    session["voter_authenticated"] = True
    session["voter_matric"] = matric_no
    log_event("LOGIN_SUCCESS", f"{matric_no} authenticated successfully")
    return redirect(url_for("ballot"))


@app.route("/ballot", methods=["GET", "POST"])
def ballot():
    if not session.get("voter_authenticated"):
        flash("Please log in to access the ballot.", "error")
        return redirect(url_for("login"))

    matric_no = session["voter_matric"]
    conn = get_db_connection()

    student = conn.execute("SELECT * FROM students WHERE matric_no = ?", (matric_no,)).fetchone()
    if student["has_voted"]:
        conn.close()
        session.clear()
        flash("You have already voted.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        candidates = conn.execute("SELECT DISTINCT position FROM candidates").fetchall()
        positions = [row["position"] for row in candidates]

        selections = {}
        for pos in positions:
            choice = request.form.get(pos)
            if not choice:
                conn.close()
                flash(f"Please select a candidate for {pos} before submitting.", "error")
                return redirect(url_for("ballot"))
            selections[pos] = choice

        salt = secrets.token_hex(8)
        voter_token = hashlib.sha256((matric_no + salt).encode()).hexdigest()

        for pos, candidate_id in selections.items():
            conn.execute(
                "INSERT INTO votes (voter_token, candidate_id, position) VALUES (?, ?, ?)",
                (voter_token, candidate_id, pos),
            )

        conn.execute("UPDATE students SET has_voted = 1 WHERE matric_no = ?", (matric_no,))
        conn.commit()
        conn.close()

        log_event("VOTE_CAST", f"Anonymous ballot recorded (token {voter_token[:10]}...)")
        session.clear()
        return render_template("confirmation.html")

    candidates = conn.execute("SELECT * FROM candidates ORDER BY position, full_name").fetchall()
    conn.close()

    grouped = {}
    for c in candidates:
        grouped.setdefault(c["position"], []).append(c)

    return render_template("ballot.html", grouped=grouped, student=student)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db_connection()
        admin = conn.execute("SELECT * FROM admins WHERE username = ?", (username,)).fetchone()
        conn.close()

        if admin and admin["password_hash"] == hash_password(password):
            session["admin_authenticated"] = True
            session["admin_username"] = username
            log_event("ADMIN_LOGIN", f"Admin {username} logged in")
            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin credentials.", "error")
        log_event("ADMIN_LOGIN_FAILED", f"Failed admin login attempt for '{username}'")

    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    total_voters = conn.execute("SELECT COUNT(*) c FROM students").fetchone()["c"]
    total_voted = conn.execute("SELECT COUNT(*) c FROM students WHERE has_voted = 1").fetchone()["c"]
    total_candidates = conn.execute("SELECT COUNT(*) c FROM candidates").fetchone()["c"]
    election = conn.execute("SELECT * FROM election_settings ORDER BY setting_id DESC LIMIT 1").fetchone()
    recent_logs = conn.execute("SELECT * FROM audit_log ORDER BY log_id DESC LIMIT 10").fetchall()
    conn.close()

    turnout = round((total_voted / total_voters) * 100, 1) if total_voters else 0

    return render_template(
        "admin_dashboard.html",
        total_voters=total_voters,
        total_voted=total_voted,
        total_candidates=total_candidates,
        turnout=turnout,
        election=election,
        recent_logs=recent_logs,
    )


@app.route("/admin/results")
def admin_results():
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT c.position, c.full_name, COUNT(v.vote_id) AS votes
        FROM candidates c
        LEFT JOIN votes v ON v.candidate_id = c.candidate_id
        GROUP BY c.candidate_id
        ORDER BY c.position, votes DESC
        """
    ).fetchall()
    conn.close()

    results = {}
    for r in rows:
        results.setdefault(r["position"], []).append(r)

    return render_template("results.html", results=results)


@app.route("/admin/candidates")
def admin_candidates():
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))
    conn = get_db_connection()
    candidates = conn.execute("SELECT * FROM candidates ORDER BY position, full_name").fetchall()
    conn.close()
    return render_template("admin_candidates.html", candidates=candidates)


@app.route("/admin/candidates/add", methods=["POST"])
def admin_candidates_add():
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))

    matric_no = request.form.get("matric_no", "").strip().upper()
    full_name = request.form.get("full_name", "").strip()
    position = request.form.get("position", "").strip()
    department = request.form.get("department", "").strip()
    manifesto = request.form.get("manifesto", "").strip()

    if not (matric_no and full_name and position and department):
        flash("Matric number, name, position, and department are all required.", "error")
        return redirect(url_for("admin_candidates"))

    conn = get_db_connection()
    conn.execute(
        """INSERT INTO candidates (matric_no, full_name, position, department, manifesto)
           VALUES (?, ?, ?, ?, ?)""",
        (matric_no, full_name, position, department, manifesto),
    )
    conn.commit()
    conn.close()
    log_event("CANDIDATE_ADDED", f"{full_name} ({matric_no}) added for {position}")
    flash(f"{full_name} added as a candidate for {position}.", "success")
    return redirect(url_for("admin_candidates"))


@app.route("/admin/candidates/<int:candidate_id>/edit", methods=["GET", "POST"])
def admin_candidates_edit(candidate_id):
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))

    conn = get_db_connection()
    candidate = conn.execute(
        "SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)
    ).fetchone()
    if not candidate:
        conn.close()
        flash("Candidate not found.", "error")
        return redirect(url_for("admin_candidates"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        position = request.form.get("position", "").strip()
        department = request.form.get("department", "").strip()
        manifesto = request.form.get("manifesto", "").strip()

        if not (full_name and position and department):
            conn.close()
            flash("Name, position, and department are required.", "error")
            return redirect(url_for("admin_candidates_edit", candidate_id=candidate_id))

        conn.execute(
            """UPDATE candidates SET full_name = ?, position = ?, department = ?, manifesto = ?
               WHERE candidate_id = ?""",
            (full_name, position, department, manifesto, candidate_id),
        )
        conn.commit()
        conn.close()
        log_event("CANDIDATE_EDITED", f"Candidate {candidate_id} updated")
        flash("Candidate updated.", "success")
        return redirect(url_for("admin_candidates"))

    conn.close()
    return render_template("admin_candidate_edit.html", candidate=candidate)


@app.route("/admin/candidates/<int:candidate_id>/delete", methods=["POST"])
def admin_candidates_delete(candidate_id):
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))
    conn = get_db_connection()
    conn.execute("DELETE FROM candidates WHERE candidate_id = ?", (candidate_id,))
    conn.commit()
    conn.close()
    log_event("CANDIDATE_DELETED", f"Candidate {candidate_id} removed")
    flash("Candidate removed.", "success")
    return redirect(url_for("admin_candidates"))


@app.route("/admin/voters")
def admin_voters():
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))
    q = request.args.get("q", "").strip()
    conn = get_db_connection()
    if q:
        like = f"%{q}%"
        voters = conn.execute(
            """SELECT * FROM students
               WHERE matric_no LIKE ? OR full_name LIKE ? OR department LIKE ?
               ORDER BY full_name""",
            (like, like, like),
        ).fetchall()
    else:
        voters = conn.execute("SELECT * FROM students ORDER BY full_name").fetchall()
    conn.close()
    return render_template("admin_voters.html", voters=voters, q=q)


@app.route("/admin/voters/add", methods=["POST"])
def admin_voters_add():
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))

    matric_no = request.form.get("matric_no", "").strip().upper()
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    department = request.form.get("department", "").strip()

    if not (matric_no and full_name and email and department):
        flash("Matric number, name, email, and department are all required.", "error")
        return redirect(url_for("admin_voters"))

    conn = get_db_connection()
    existing = conn.execute("SELECT 1 FROM students WHERE matric_no = ?", (matric_no,)).fetchone()
    if existing:
        conn.close()
        flash(f"A voter with matric number {matric_no} is already registered.", "error")
        return redirect(url_for("admin_voters"))

    conn.execute(
        "INSERT INTO students (matric_no, full_name, email, department) VALUES (?, ?, ?, ?)",
        (matric_no, full_name, email, department),
    )
    conn.commit()
    conn.close()
    log_event("VOTER_ADDED", f"{full_name} ({matric_no}) registered to vote")
    flash(f"{full_name} ({matric_no}) registered to vote.", "success")
    return redirect(url_for("admin_voters"))


@app.route("/admin/voters/bulk", methods=["POST"])
def admin_voters_bulk():
    """Register many voters at once, from a pasted list or an uploaded CSV file.

    Accepted line format (one voter per line), comma-separated:
        matric_no, full_name, email, department
    A header row (e.g. "matric_no,full_name,email,department") is detected
    and skipped automatically. Blank lines are ignored.
    """
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))

    raw_text = request.form.get("bulk_text", "")
    uploaded = request.files.get("bulk_file")
    if uploaded and uploaded.filename:
        raw_text = uploaded.read().decode("utf-8", errors="ignore")

    if not raw_text.strip():
        flash("Paste a list of voters or choose a CSV file to upload.", "error")
        return redirect(url_for("admin_voters"))

    conn = get_db_connection()
    added, skipped, duplicates = 0, 0, 0

    for line_no, line in enumerate(raw_text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            skipped += 1
            continue
        matric_no, full_name, email, department = parts[0], parts[1], parts[2], parts[3]
        if matric_no.lower() in ("matric_no", "matric no", "matriculation number"):
            continue  # header row
        if not (matric_no and full_name and email and department):
            skipped += 1
            continue

        matric_no = matric_no.upper()
        existing = conn.execute("SELECT 1 FROM students WHERE matric_no = ?", (matric_no,)).fetchone()
        if existing:
            duplicates += 1
            continue

        conn.execute(
            "INSERT INTO students (matric_no, full_name, email, department) VALUES (?, ?, ?, ?)",
            (matric_no, full_name, email, department),
        )
        added += 1

    conn.commit()
    conn.close()
    log_event("VOTERS_BULK_ADDED", f"{added} added, {duplicates} duplicates skipped, {skipped} invalid lines skipped")
    flash(
        f"Bulk upload complete: {added} voter(s) added, "
        f"{duplicates} already registered (skipped), {skipped} invalid line(s) skipped.",
        "success" if added else "error",
    )
    return redirect(url_for("admin_voters"))


@app.route("/admin/voters/<int:student_id>/delete", methods=["POST"])
def admin_voters_delete(student_id):
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))
    conn = get_db_connection()
    conn.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
    conn.commit()
    conn.close()
    log_event("VOTER_DELETED", f"Student {student_id} removed from register")
    flash("Voter removed from register.", "success")
    return redirect(url_for("admin_voters"))


@app.route("/admin/voters/<int:student_id>/reset-vote", methods=["POST"])
def admin_voters_reset_vote(student_id):
    """Allow an admin to clear a voter's has_voted flag, e.g. to correct a
    mistaken entry. This does NOT delete or alter any already-cast ballots
    in the votes table (which are anonymous and cannot be traced back to
    this student), so using it after the fact can allow a second vote to
    be cast. Intended for pre-election corrections only."""
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))
    conn = get_db_connection()
    conn.execute("UPDATE students SET has_voted = 0 WHERE student_id = ?", (student_id,))
    conn.commit()
    conn.close()
    log_event("VOTER_RESET", f"Voting status reset for student {student_id}")
    flash("Voter's status reset — they can log in and vote again.", "success")
    return redirect(url_for("admin_voters"))


@app.route("/admin/toggle-election", methods=["POST"])
def toggle_election():
    if not session.get("admin_authenticated"):
        return redirect(url_for("admin_login"))
    conn = get_db_connection()
    election = conn.execute("SELECT * FROM election_settings ORDER BY setting_id DESC LIMIT 1").fetchone()
    new_state = 0 if election["is_active"] else 1
    conn.execute("UPDATE election_settings SET is_active = ? WHERE setting_id = ?", (new_state, election["setting_id"]))
    conn.commit()
    conn.close()
    log_event("ELECTION_TOGGLED", f"Election active state set to {new_state}")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)
