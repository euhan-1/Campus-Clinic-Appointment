# Campus Clinic Appointment Scheduling and Records Management System
University of Batangas - Health Services Office (Systems Analysis and Design project)

Python + Flask + SQLite. No ORM, plain SQL, one `app.py`.

## How to run
1. Install Python 3.9+ from python.org.
2. Open a terminal in this folder and run:
   ```
   pip install -r requirements.txt
   python app.py
   ```
3. Open http://127.0.0.1:5000

The first run creates `clinic.db` from `schema.sql` and loads sample data. To reset everything, stop the app, delete `clinic.db`, and run again.
`python test_app.py` runs a quick check of the main rules (uses a temporary database).

## Sample logins (all passwords: `password123`)
| Role | Username |
|---|---|
| Administrator | `admin` |
| Nurse | `nurse` |
| Doctor (Physician, Mon-Fri) | `PRC-100234` |
| Doctor (Dentist, Mon/Wed/Fri) | `PRC-200456` |
| Patient | `2024-0001`, `2024-0002`, `EMP-0100` |

## Files
- `schema.sql` - the 7 tables (fields exactly as in the data dictionary, foreign keys as in the ERD)
- `app.py` - all pages, rules and sample data
- `templates/` - HTML pages (`base.html` holds the menu and layout)

## What each role can do (matches DFD processes 1.0-6.0)
| Role | Screens |
|---|---|
| Patient | Doctor Schedules, Book Appointment, My Appointments (cancel), My Information |
| Nurse | Appointments (mark No-show / Cancel), Record Visit (walk-in, today), Patients (search/register), Doctor Schedules, Monthly Report |
| Doctor | My Appointments, Record Consultation (sets Completed), Patient Records (with consultation history), My Schedule (add / make Unavailable / delete) |
| Administrator | User Accounts (add, activate/deactivate, reset password), Monthly Report |

## Booking rules (DFD 3.0 Process Appointments)
1. 3.1 Patient picks a date and visit type (Dental -> Dentist; Medical / Follow-up -> Physician).
2. 3.2 `open_schedules()` checks DOCTOR_SCHEDULE: doctor works that weekday, schedule is Available, doctor is Active, and appointments that day (not Cancelled / No-show) are fewer than `slot_limit`.
3. If nothing is open, the page says so and suggests the next 3 days with open slots (looks up to 30 days ahead).
4. 3.3 If a slot is open, the appointment is saved as **Confirmed** automatically. The time is spread evenly over the clinic hours (slot 1 at the start time, and so on).
5. 3.4 Nurse can mark Confirmed appointments No-show or Cancelled; the doctor's consultation marks them Completed.

## Decisions worth knowing (explain these in your defense)
- **How a login finds its patient/doctor:** USER_ACCOUNT has no patient_id/doctor_id in the ERD, so the link is by username. Patient username = `student_number`; Doctor username = `license_number`. The admin form checks that they exist.
- **Registering a patient** (nurse) also creates the patient's login: username and first password = the student/employee number.
- **Passwords** are stored hashed (PBKDF2), never plain text.
- **Walk-in "Record Visit"** books an appointment for today with the same slot rules, so the doctor can then record the consultation.
- **Monthly report numbers:** visits = appointments in the month not Cancelled/No-show; consultations = CONSULTATION_RECORD rows; first aid = consultations with first aid filled in; referrals = referred to hospital.
- Doctors are only in the sample data; no screen adds doctors (not in the role list).

## Not included (keep it simple)
CSRF protection, email/SMS, password rules, editing patient records, report export. Add if the panel asks.
