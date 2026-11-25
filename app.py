"""Campus Clinic Appointment Scheduling and Records Management System
University of Batangas - Health Services Office

One file, plain SQL, no ORM. Run:  python app.py
Sections: setup -> helpers -> login -> patient -> nurse/doctor -> admin -> sample data
"""
import calendar
import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "change-this-secret-key"  # needed for login sessions
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clinic.db")


# ---------------------------------------------------------------- setup ----
def get_db():
    """One database connection per request."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row          # lets us use row["column_name"]
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db:
        db.close()


def q(sql, args=(), one=False):
    """Run a SELECT. one=True returns a single row (or None)."""
    rows = get_db().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def run(sql, args=()):
    """Run an INSERT/UPDATE/DELETE and save it. Returns the new row id."""
    cur = get_db().execute(sql, args)
    get_db().commit()
    return cur.lastrowid


def hash_pw(password):
    # salt_length=8 keeps the hash under the 100 characters allowed by USER_ACCOUNT.password
    return generate_password_hash(password, method="pbkdf2:sha256", salt_length=8)


# -------------------------------------------------------------- helpers ----
def login_required(*roles):
    """Page is for logged-in users; if roles are given, only those roles."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "role" not in session:
                return redirect(url_for("login"))
            if roles and session["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


def my_patient():
    """The PATIENT row of the logged-in patient (username = student number)."""
    return q("SELECT * FROM PATIENT WHERE student_number=?", (session["username"],), one=True)


def my_doctor():
    """The DOCTOR row of the logged-in doctor (username = PRC license number)."""
    return q("SELECT * FROM DOCTOR WHERE license_number=?", (session["username"],), one=True)


def parse_date(text):
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def open_schedules(day, visit_type):
    """Schedules with free slots on this date. Empty list = booking not possible.
    Rules: doctor works that weekday, schedule Available, doctor Active,
    right kind of doctor (Dental -> Dentist, otherwise Physician), slots not full."""
    specialization = "Dentist" if visit_type == "Dental" else "Physician"
    rows = q("""
        SELECT s.*, d.first_name, d.last_name, d.specialization,
               (SELECT COUNT(*) FROM APPOINTMENT a
                 WHERE a.schedule_id = s.schedule_id AND a.appointment_date = ?
                   AND a.status NOT IN ('Cancelled', 'No-show')) AS used
        FROM DOCTOR_SCHEDULE s JOIN DOCTOR d ON d.doctor_id = s.doctor_id
        WHERE s.day_of_week = ? AND s.availability_status = 'Available'
          AND d.status = 'Active' AND d.specialization = ?
    """, (day.isoformat(), day.strftime("%A"), specialization))
    return [r for r in rows if r["used"] < r["slot_limit"]]


def next_open_days(day, visit_type, how_many=3):
    """Suggest the next days (up to 30 ahead) that still have open slots."""
    found = []
    for i in range(1, 31):
        nxt = day + timedelta(days=i)
        slots = open_schedules(nxt, visit_type)
        if slots:
            found.append((nxt, sum(s["slot_limit"] - s["used"] for s in slots)))
        if len(found) == how_many:
            break
    return found


def slot_time(s):
    """Spread the slots evenly over the clinic hours: slot n starts at start + n*step."""
    h1, m1 = map(int, s["time_start"].split(":")[:2])
    h2, m2 = map(int, s["time_end"].split(":")[:2])
    start = h1 * 60 + m1
    step = max(((h2 * 60 + m2) - start) // s["slot_limit"], 1)
    t = start + s["used"] * step
    return f"{t // 60:02d}:{t % 60:02d}"


@app.context_processor
def inject_today():
    return {"today": date.today().isoformat()}


# ---------------------------------------------------------------- login ----
@app.route("/")
def index():
    if "role" not in session:
        return redirect(url_for("login"))
    home = {"Patient": "my_appointments", "Nurse": "appointments",
            "Doctor": "appointments", "Administrator": "users"}
    return redirect(url_for(home[session["role"]]))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = q("SELECT * FROM USER_ACCOUNT WHERE username=?",
                 (request.form["username"].strip(),), one=True)
        if user and user["status"] == "Active" and check_password_hash(user["password"], request.form["password"]):
            session.clear()
            session.update(user_id=user["user_id"], username=user["username"],
                           role=user["role"], full_name=user["full_name"])
            return redirect(url_for("index"))
        flash("Wrong username or password, or the account is inactive.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -------------------------------------------------------------- patient ----
@app.route("/schedules")
@login_required("Patient", "Nurse")
def schedules():
    rows = q("""SELECT s.*, d.first_name, d.last_name, d.specialization
                FROM DOCTOR_SCHEDULE s JOIN DOCTOR d ON d.doctor_id = s.doctor_id
                WHERE d.status = 'Active'
                ORDER BY d.last_name, s.time_start""")
    days = list(calendar.day_name)
    rows = sorted(rows, key=lambda r: days.index(r["day_of_week"]))
    return render_template("schedules.html", rows=rows)


@app.route("/book", methods=["GET", "POST"])
@login_required("Patient", "Nurse")
def book():
    """Patients book any future date. The nurse uses this page to record a walk-in visit (today only)."""
    is_nurse = session["role"] == "Nurse"
    form = request.values
    visit_type = form.get("visit_type", "Medical")
    day = date.today() if is_nurse else parse_date(form.get("date"))

    if is_nurse:
        patient = q("SELECT * FROM PATIENT WHERE student_number=?",
                    (form.get("student_number", "").strip(),), one=True)
        if form.get("student_number") and not patient:
            flash("No patient with that student/employee number. Register the patient first.", "error")
    else:
        patient = my_patient()
        if not patient:
            abort(404)
    if day and day < date.today():
        flash("Please choose today or a future date.", "error")
        day = None

    options = open_schedules(day, visit_type) if day and patient else []
    suggestions = next_open_days(day, visit_type) if day and patient and not options else []

    if request.method == "POST" and patient and day:
        reason = form.get("reason", "").strip()
        chosen = next((s for s in options if str(s["schedule_id"]) == form.get("schedule_id")), None)
        if not reason:
            flash("Please enter the reason for the visit.", "error")
        elif not chosen:
            flash("That slot is no longer available. Please choose again.", "error")
        else:
            # Slot is free, so the appointment is auto-confirmed.
            run("""INSERT INTO APPOINTMENT (patient_id, schedule_id, appointment_date, appointment_time,
                                            visit_type, reason, status, date_requested)
                   VALUES (?, ?, ?, ?, ?, ?, 'Confirmed', ?)""",
                (patient["patient_id"], chosen["schedule_id"], day.isoformat(), slot_time(chosen),
                 visit_type, reason[:100], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            flash(f"Appointment confirmed: {day.isoformat()} at {slot_time(chosen)}.", "ok")
            return redirect(url_for("appointments" if is_nurse else "my_appointments"))

    return render_template("book.html", is_nurse=is_nurse, patient=patient, day=day,
                           visit_type=visit_type, options=options, suggestions=suggestions,
                           slot_time=slot_time, form=form)


@app.route("/my-appointments")
@login_required("Patient")
def my_appointments():
    patient = my_patient() or abort(404)
    rows = q("""SELECT a.*, d.first_name, d.last_name
                FROM APPOINTMENT a
                JOIN DOCTOR_SCHEDULE s ON s.schedule_id = a.schedule_id
                JOIN DOCTOR d ON d.doctor_id = s.doctor_id
                WHERE a.patient_id = ? ORDER BY a.appointment_date DESC, a.appointment_time DESC""",
             (patient["patient_id"],))
    return render_template("my_appointments.html", rows=rows)


@app.route("/cancel/<int:appointment_id>", methods=["POST"])
@login_required("Patient")
def cancel(appointment_id):
    patient = my_patient() or abort(404)
    appt = q("SELECT * FROM APPOINTMENT WHERE appointment_id=? AND patient_id=?",
             (appointment_id, patient["patient_id"]), one=True) or abort(404)
    if appt["status"] in ("Pending", "Confirmed"):
        run("UPDATE APPOINTMENT SET status='Cancelled' WHERE appointment_id=?", (appointment_id,))
        flash("Appointment cancelled.", "ok")
    return redirect(url_for("my_appointments"))


@app.route("/me")
@login_required("Patient")
def me():
    return render_template("patient.html", p=my_patient() or abort(404), consults=None)


# --------------------------------------------------- nurse and doctor ------
@app.route("/appointments")
@login_required("Nurse", "Doctor")
def appointments():
    """Nurse sees everyone's appointments; doctor sees only their own. Default: today."""
    when = request.args.get("date", date.today().isoformat())
    sql = """SELECT a.*, p.first_name AS pfirst, p.last_name AS plast, p.student_number,
                    d.first_name AS dfirst, d.last_name AS dlast
             FROM APPOINTMENT a
             JOIN PATIENT p ON p.patient_id = a.patient_id
             JOIN DOCTOR_SCHEDULE s ON s.schedule_id = a.schedule_id
             JOIN DOCTOR d ON d.doctor_id = s.doctor_id WHERE 1=1"""
    args = []
    if session["role"] == "Doctor":
        sql += " AND d.doctor_id = ?"
        args.append((my_doctor() or abort(404))["doctor_id"])
    if when != "all":
        sql += " AND a.appointment_date = ?"
        args.append(when)
    sql += " ORDER BY a.appointment_date DESC, a.appointment_time LIMIT 200"
    return render_template("appointments.html", rows=q(sql, args), when=when)


@app.route("/status/<int:appointment_id>", methods=["POST"])
@login_required("Nurse")
def update_status(appointment_id):
    new = request.form.get("status")
    if new not in ("No-show", "Cancelled"):
        abort(400)
    run("UPDATE APPOINTMENT SET status=? WHERE appointment_id=? AND status IN ('Pending','Confirmed')",
        (new, appointment_id))
    flash(f"Appointment marked {new}.", "ok")
    return redirect(request.referrer or url_for("appointments"))


@app.route("/consult/<int:appointment_id>", methods=["GET", "POST"])
@login_required("Doctor")
def consult(appointment_id):
    doctor = my_doctor() or abort(404)
    appt = q("""SELECT a.*, p.first_name, p.last_name FROM APPOINTMENT a
                JOIN PATIENT p ON p.patient_id = a.patient_id
                JOIN DOCTOR_SCHEDULE s ON s.schedule_id = a.schedule_id
                WHERE a.appointment_id = ? AND s.doctor_id = ?""",
             (appointment_id, doctor["doctor_id"]), one=True) or abort(404)
    if appt["status"] != "Confirmed":
        flash("Only Confirmed appointments can be consulted.", "error")
        return redirect(url_for("appointments"))

    if request.method == "POST":
        f = request.form
        complaint = f.get("complaint", "").strip()
        if not complaint:
            flash("Complaint is required.", "error")
        else:
            followup = 1 if f.get("followup_required") else 0
            run("""INSERT INTO CONSULTATION_RECORD
                   (appointment_id, patient_id, doctor_id, consultation_date, complaint, first_aid_given,
                    findings, medicine_given, lab_request, followup_required, followup_date,
                    referred_to_hospital, remarks)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (appointment_id, appt["patient_id"], doctor["doctor_id"], appt["appointment_date"],
                 complaint[:150], f.get("first_aid_given", "")[:150] or None,
                 f.get("findings", "")[:200] or None, f.get("medicine_given", "")[:150] or None,
                 f.get("lab_request", "")[:100] or None, followup,
                 (f.get("followup_date") or None) if followup else None,
                 1 if f.get("referred_to_hospital") else 0, f.get("remarks", "")[:200] or None))
            run("UPDATE APPOINTMENT SET status='Completed' WHERE appointment_id=?", (appointment_id,))
            flash("Consultation recorded. Appointment marked Completed.", "ok")
            return redirect(url_for("appointments"))
    return render_template("consult.html", a=appt)


@app.route("/patients")
@login_required("Nurse", "Doctor")
def patients():
    term = request.args.get("q", "").strip()
    like = f"%{term}%"
    rows = q("""SELECT * FROM PATIENT
                WHERE student_number LIKE ? OR last_name LIKE ? OR first_name LIKE ?
                ORDER BY last_name, first_name LIMIT 50""", (like, like, like))
    return render_template("patients.html", rows=rows, term=term)


@app.route("/patients/new", methods=["GET", "POST"])
@login_required("Nurse")
def patient_new():
    f = request.form
    if request.method == "POST":
        number = f["student_number"].strip()
        try:
            run("""INSERT INTO PATIENT (student_number, patient_type, last_name, first_name, middle_name,
                       department, year_level, contact_number, email, guardian_name, guardian_contact,
                       date_registered) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (number, f["patient_type"], f["last_name"].strip(), f["first_name"].strip(),
                 f.get("middle_name", "").strip() or None, f["department"].strip(),
                 f.get("year_level", "").strip() or None, f["contact_number"].strip(),
                 f.get("email", "").strip() or None, f.get("guardian_name", "").strip() or None,
                 f.get("guardian_contact", "").strip() or None, date.today().isoformat()))
        except sqlite3.IntegrityError:
            flash("That student/employee number is already registered.", "error")
            return render_template("patient_new.html", f=f)
        # Give the patient a login: username = student number, first password = student number.
        run("""INSERT INTO USER_ACCOUNT (username, password, full_name, role, status, date_created)
               VALUES (?,?,?,?,?,?)""",
            (number, hash_pw(number), f"{f['first_name'].strip()} {f['last_name'].strip()}",
             "Patient", "Active", date.today().isoformat()))
        flash(f"Patient registered. Login: {number} / password: {number}", "ok")
        return redirect(url_for("patients", q=number))
    return render_template("patient_new.html", f=f)


@app.route("/patients/<int:patient_id>")
@login_required("Nurse", "Doctor")
def patient_view(patient_id):
    p = q("SELECT * FROM PATIENT WHERE patient_id=?", (patient_id,), one=True) or abort(404)
    consults = None
    if session["role"] == "Doctor":       # only doctors see medical history
        consults = q("""SELECT c.*, d.last_name AS dlast FROM CONSULTATION_RECORD c
                        JOIN DOCTOR d ON d.doctor_id = c.doctor_id
                        WHERE c.patient_id=? ORDER BY c.consultation_date DESC""", (patient_id,))
    return render_template("patient.html", p=p, consults=consults)


@app.route("/my-schedule", methods=["GET", "POST"])
@login_required("Doctor")
def my_schedule():
    doctor = my_doctor() or abort(404)
    if request.method == "POST":
        f = request.form
        try:
            limit = int(f["slot_limit"])
        except ValueError:
            limit = 0
        if f["day_of_week"] not in calendar.day_name or f["time_end"] <= f["time_start"] or limit < 1:
            flash("Check the form: end time must be after start time and slots must be at least 1.", "error")
        else:
            run("""INSERT INTO DOCTOR_SCHEDULE (doctor_id, day_of_week, time_start, time_end, slot_limit,
                                                availability_status) VALUES (?,?,?,?,?,'Available')""",
                (doctor["doctor_id"], f["day_of_week"], f["time_start"], f["time_end"], limit))
            flash("Schedule added.", "ok")
        return redirect(url_for("my_schedule"))
    rows = q("SELECT * FROM DOCTOR_SCHEDULE WHERE doctor_id=?", (doctor["doctor_id"],))
    days = list(calendar.day_name)
    return render_template("my_schedule.html", rows=sorted(rows, key=lambda r: days.index(r["day_of_week"])),
                           days=days)


@app.route("/my-schedule/<int:schedule_id>/<action>", methods=["POST"])
@login_required("Doctor")
def schedule_action(schedule_id, action):
    doctor = my_doctor() or abort(404)
    s = q("SELECT * FROM DOCTOR_SCHEDULE WHERE schedule_id=? AND doctor_id=?",
          (schedule_id, doctor["doctor_id"]), one=True) or abort(404)
    if action == "toggle":
        new = "Unavailable" if s["availability_status"] == "Available" else "Available"
        run("UPDATE DOCTOR_SCHEDULE SET availability_status=? WHERE schedule_id=?", (new, schedule_id))
    elif action == "delete":
        if q("SELECT 1 FROM APPOINTMENT WHERE schedule_id=?", (schedule_id,), one=True):
            flash("This schedule has appointments. Mark it Unavailable instead.", "error")
        else:
            run("DELETE FROM DOCTOR_SCHEDULE WHERE schedule_id=?", (schedule_id,))
    else:
        abort(404)
    return redirect(url_for("my_schedule"))


# ---------------------------------------------------------------- admin ----
@app.route("/users", methods=["GET", "POST"])
@login_required("Administrator")
def users():
    if request.method == "POST":
        f = request.form
        username, role = f["username"].strip(), f["role"]
        # Patient/Doctor logins must match an existing patient number / license number.
        linked_ok = (
            (role == "Patient" and q("SELECT 1 FROM PATIENT WHERE student_number=?", (username,), one=True))
            or (role == "Doctor" and q("SELECT 1 FROM DOCTOR WHERE license_number=?", (username,), one=True))
            or role in ("Nurse", "Administrator"))
        if not (username and f["password"] and f["full_name"].strip()) or role not in (
                "Patient", "Nurse", "Doctor", "Administrator"):
            flash("Fill in all fields.", "error")
        elif not linked_ok:
            flash("For Patient use the student number; for Doctor use the PRC license number (must already exist).", "error")
        else:
            try:
                run("""INSERT INTO USER_ACCOUNT (username, password, full_name, role, status, date_created)
                       VALUES (?,?,?,?,'Active',?)""",
                    (username, hash_pw(f["password"]), f["full_name"].strip(), role, date.today().isoformat()))
                flash("Account created.", "ok")
            except sqlite3.IntegrityError:
                flash("Username already exists.", "error")
        return redirect(url_for("users"))
    return render_template("users.html", rows=q("SELECT * FROM USER_ACCOUNT ORDER BY role, username"))


@app.route("/users/<int:user_id>/<action>", methods=["POST"])
@login_required("Administrator")
def user_action(user_id, action):
    u = q("SELECT * FROM USER_ACCOUNT WHERE user_id=?", (user_id,), one=True) or abort(404)
    if action == "toggle" and user_id != session["user_id"]:     # can't lock yourself out
        run("UPDATE USER_ACCOUNT SET status=? WHERE user_id=?",
            ("Inactive" if u["status"] == "Active" else "Active", user_id))
    elif action == "reset" and request.form.get("new_password"):
        run("UPDATE USER_ACCOUNT SET password=? WHERE user_id=?", (hash_pw(request.form["new_password"]), user_id))
        flash(f"Password reset for {u['username']}.", "ok")
    return redirect(url_for("users"))


@app.route("/report", methods=["GET", "POST"])
@login_required("Nurse", "Administrator")
def report():
    if request.method == "POST":
        try:
            month, year = int(request.form["month"]), int(request.form["year"])
            assert 1 <= month <= 12 and 2000 <= year <= 2100
        except (ValueError, AssertionError):
            flash("Choose a valid month and year.", "error")
            return redirect(url_for("report"))
        ym = f"{year}-{month:02d}"                 # appointment/consultation dates start with this
        count = lambda sql: q(sql, (ym,), one=True)[0]
        run("""INSERT INTO MONTHLY_REPORT (report_month, report_year, total_visits, total_consultations,
                   total_first_aid, total_referrals, generated_by, date_generated) VALUES (?,?,?,?,?,?,?,?)""",
            (calendar.month_name[month], year,
             # visits = appointments in the month that were not cancelled or no-show
             count("SELECT COUNT(*) FROM APPOINTMENT WHERE substr(appointment_date,1,7)=? "
                   "AND status NOT IN ('Cancelled','No-show')"),
             count("SELECT COUNT(*) FROM CONSULTATION_RECORD WHERE substr(consultation_date,1,7)=?"),
             count("SELECT COUNT(*) FROM CONSULTATION_RECORD WHERE substr(consultation_date,1,7)=? "
                   "AND first_aid_given IS NOT NULL AND first_aid_given <> ''"),
             count("SELECT COUNT(*) FROM CONSULTATION_RECORD WHERE substr(consultation_date,1,7)=? "
                   "AND referred_to_hospital=1"),
             session["user_id"], date.today().isoformat()))
        flash("Report generated.", "ok")
        return redirect(url_for("report"))
    rows = q("""SELECT r.*, u.full_name FROM MONTHLY_REPORT r
                JOIN USER_ACCOUNT u ON u.user_id = r.generated_by ORDER BY r.report_id DESC""")
    return render_template("report.html", rows=rows, months=list(calendar.month_name)[1:])


# ---------------------------------------------------------- sample data ----
def last_weekday(before, back=0):
    """A recent Mon-Fri date: the weekday `back` weekdays before `before`."""
    d = before
    while back >= 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            back -= 1
    return d


def init_db():
    """Create tables and sample data. Runs once, when clinic.db does not exist yet."""
    db = sqlite3.connect(DB_FILE)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")) as f:
        db.executescript(f.read())
    today = date.today()
    pw = hash_pw("password123")

    # Doctors: a physician (Mon-Fri) and a dentist (Mon/Wed/Fri only)
    db.executemany("INSERT INTO DOCTOR (last_name, first_name, specialization, license_number, contact_number, "
                   "employment_type, status) VALUES (?,?,?,?,?,?,?)", [
        ("Reyes", "Maria", "Physician", "PRC-100234", "09171234567", "Full-time", "Active"),
        ("Santos", "Jose", "Dentist", "PRC-200456", "09181234567", "Part-time", "Active")])
    sched = [(1, d, "08:00", "12:00", 6, "Available") for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")]
    sched += [(2, d, "13:00", "16:00", 3, "Available") for d in ("Monday", "Wednesday", "Friday")]
    db.executemany("INSERT INTO DOCTOR_SCHEDULE (doctor_id, day_of_week, time_start, time_end, slot_limit, "
                   "availability_status) VALUES (?,?,?,?,?,?)", sched)

    # Patients
    d0 = today.isoformat()
    db.executemany("""INSERT INTO PATIENT (student_number, patient_type, last_name, first_name, middle_name,
        department, year_level, contact_number, email, guardian_name, guardian_contact, date_registered)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", [
        ("2024-0001", "Student", "Dela Cruz", "Juan", "Perez", "College of Engineering", "2nd Year",
         "09201112222", "juan@example.com", "Ana Dela Cruz", "09203334444", d0),
        ("2024-0002", "Student", "Garcia", "Lea", None, "College of Nursing", "3rd Year",
         "09205556666", None, "Pedro Garcia", "09207778888", d0),
        ("EMP-0100", "Faculty", "Mendoza", "Carlo", "A.", "College of Business", None,
         "09209990000", "carlo@example.com", None, None, d0)])

    # Accounts (every sample password is password123)
    db.executemany("INSERT INTO USER_ACCOUNT (username, password, full_name, role, status, date_created) "
                   "VALUES (?,?,?,?,'Active',?)", [
        ("admin", pw, "Clinic Administrator", "Administrator", d0),
        ("nurse", pw, "Nurse Rosa Villanueva", "Nurse", d0),
        ("PRC-100234", pw, "Dr. Maria Reyes", "Doctor", d0),
        ("PRC-200456", pw, "Dr. Jose Santos", "Doctor", d0),
        ("2024-0001", pw, "Juan Dela Cruz", "Patient", d0),
        ("2024-0002", pw, "Lea Garcia", "Patient", d0),
        ("EMP-0100", pw, "Carlo Mendoza", "Patient", d0)])

    # One finished visit (with consultation) and one upcoming appointment for Juan
    past = last_weekday(today, 2)
    nxt = today
    while True:
        nxt += timedelta(days=1)
        if nxt.weekday() < 5:
            break
    sid = lambda dt: db.execute("SELECT schedule_id FROM DOCTOR_SCHEDULE WHERE doctor_id=1 AND day_of_week=?",
                                (dt.strftime("%A"),)).fetchone()[0]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO APPOINTMENT (patient_id, schedule_id, appointment_date, appointment_time, visit_type, "
               "reason, status, date_requested) VALUES (1,?,?,'08:00','Medical','Fever and headache','Completed',?)",
               (sid(past), past.isoformat(), now))
    db.execute("INSERT INTO CONSULTATION_RECORD (appointment_id, patient_id, doctor_id, consultation_date, complaint,"
               " first_aid_given, findings, medicine_given, lab_request, followup_required, followup_date,"
               " referred_to_hospital, remarks) VALUES (1,1,1,?,'Fever and headache',NULL,'Viral infection',"
               "'Paracetamol 500mg',NULL,0,NULL,0,'Rest and fluids')", (past.isoformat(),))
    db.execute("INSERT INTO APPOINTMENT (patient_id, schedule_id, appointment_date, appointment_time, visit_type, "
               "reason, status, date_requested) VALUES (1,?,?,'08:00','Medical','Medical certificate','Confirmed',?)",
               (sid(nxt), nxt.isoformat(), now))
    db.commit()
    db.close()


if __name__ == "__main__":
    if not os.path.exists(DB_FILE):
        init_db()
        print("Created clinic.db with sample data.")
    app.run(debug=False)
