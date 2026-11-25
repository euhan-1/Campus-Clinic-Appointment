"""Quick smoke test of the main rules. Run: python test_app.py  (uses a temporary database)"""
import os
import tempfile
from datetime import date, timedelta

import app as clinic

clinic.DB_FILE = os.path.join(tempfile.mkdtemp(), "test.db")
clinic.init_db()
c = clinic.app.test_client()


def login(user, pw="password123"):
    c.get("/logout")
    r = c.post("/login", data={"username": user, "password": pw}, follow_redirects=True)
    assert b"Log out" in r.data, f"login failed for {user}"


def next_day(weekday):  # next date (after today) that falls on this weekday number, Mon=0
    d = date.today() + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


# wrong password is refused
assert b"Wrong username" in c.post("/login", data={"username": "nurse", "password": "x"}).data

# patient: dentist works Mon/Wed/Fri only -> Tuesday dental booking is refused with suggestions
login("2024-0001")
tue = next_day(1)
r = c.get(f"/book?date={tue}&visit_type=Dental")
assert b"No Dental slots" in r.data and b"Next days with open slots" in r.data

# book a dental slot on Monday until full (3 slots); the 4th person is refused
mon = next_day(0)
with clinic.app.app_context():
    sid = clinic.open_schedules(mon, "Dental")[0]["schedule_id"]
for i in range(3):
    r = c.post("/book", data={"date": mon, "visit_type": "Dental", "schedule_id": sid, "reason": "Toothache"},
               follow_redirects=True)
    assert b"Appointment confirmed" in r.data and b"Confirmed" in r.data
assert b"all slots are full" in c.get(f"/book?date={mon}&visit_type=Dental").data

# patient cancels, slot opens again
with clinic.app.app_context():
    appt_id = clinic.q("SELECT MAX(appointment_id) FROM APPOINTMENT")[0][0]
c.post(f"/cancel/{appt_id}")
assert b"all slots are full" not in c.get(f"/book?date={mon}&visit_type=Dental").data

# doctor records a consultation -> appointment Completed
login("PRC-100234")
r = c.get("/appointments?date=all")
assert b"Record consultation" in r.data
c.post("/consult/2", data={"complaint": "Cough", "first_aid_given": "Rest", "referred_to_hospital": "on"})
with clinic.app.app_context():
    assert clinic.q("SELECT status FROM APPOINTMENT WHERE appointment_id=2")[0][0] == "Completed"

# nurse: register patient, mark no-show, report counts the consultation
login("nurse")
c.post("/patients/new", data={"student_number": "2025-9", "patient_type": "Student", "last_name": "Lim",
                              "first_name": "Ana", "department": "CAS", "contact_number": "0917"})
login("2025-9", "2025-9")  # new patient can log in with the number
login("nurse")
c.post("/status/3", data={"status": "No-show"})
c.post("/report", data={"month": date.today().month, "year": date.today().year})
with clinic.app.app_context():
    row = clinic.q("SELECT * FROM MONTHLY_REPORT")[0]
assert row["total_referrals"] == 1 and row["total_first_aid"] == 1, dict(row)

# roles are enforced
login("2024-0001")
assert c.get("/users").status_code == 403 and c.get("/report").status_code == 403

# admin can open the user list
login("admin")
assert b"nurse" in c.get("/users").data
print("All checks passed.")
