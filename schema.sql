-- Campus Clinic database (SQLite). 7 tables, fields exactly as in the data dictionary.
PRAGMA foreign_keys = ON;

CREATE TABLE PATIENT (
    patient_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    student_number   VARCHAR(15) NOT NULL UNIQUE,
    patient_type     VARCHAR(15) NOT NULL,            -- Student, Faculty, Staff
    last_name        VARCHAR(30) NOT NULL,
    first_name       VARCHAR(30) NOT NULL,
    middle_name      VARCHAR(30),
    department       VARCHAR(50) NOT NULL,
    year_level       VARCHAR(15),
    contact_number   VARCHAR(15) NOT NULL,
    email            VARCHAR(50),
    guardian_name    VARCHAR(60),
    guardian_contact VARCHAR(15),
    date_registered  DATE NOT NULL
);

CREATE TABLE DOCTOR (
    doctor_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    last_name       VARCHAR(30) NOT NULL,
    first_name      VARCHAR(30) NOT NULL,
    specialization  VARCHAR(30) NOT NULL,             -- Physician, Dentist
    license_number  VARCHAR(20) NOT NULL UNIQUE,
    contact_number  VARCHAR(15),
    employment_type VARCHAR(20) NOT NULL,             -- Full-time, Part-time
    status          VARCHAR(15) NOT NULL              -- Active, Inactive
);

CREATE TABLE DOCTOR_SCHEDULE (
    schedule_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id           INTEGER NOT NULL REFERENCES DOCTOR(doctor_id),
    day_of_week         VARCHAR(10) NOT NULL,         -- Monday ... Sunday
    time_start          TIME NOT NULL,                -- 'HH:MM'
    time_end            TIME NOT NULL,
    slot_limit          INTEGER NOT NULL,
    availability_status VARCHAR(15) NOT NULL          -- Available, Unavailable
);

CREATE TABLE APPOINTMENT (
    appointment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id       INTEGER NOT NULL REFERENCES PATIENT(patient_id),
    schedule_id      INTEGER NOT NULL REFERENCES DOCTOR_SCHEDULE(schedule_id),
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    visit_type       VARCHAR(20) NOT NULL,            -- Medical, Dental, Follow-up
    reason           VARCHAR(100) NOT NULL,
    status           VARCHAR(15) NOT NULL,            -- Pending, Confirmed, Completed, Cancelled, No-show
    date_requested   DATETIME NOT NULL
);

CREATE TABLE CONSULTATION_RECORD (
    consultation_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id       INTEGER NOT NULL REFERENCES APPOINTMENT(appointment_id),
    patient_id           INTEGER NOT NULL REFERENCES PATIENT(patient_id),
    doctor_id            INTEGER NOT NULL REFERENCES DOCTOR(doctor_id),
    consultation_date    DATE NOT NULL,
    complaint            VARCHAR(150) NOT NULL,
    first_aid_given      VARCHAR(150),
    findings             VARCHAR(200),
    medicine_given       VARCHAR(150),
    lab_request          VARCHAR(100),
    followup_required    BOOLEAN NOT NULL CHECK (followup_required IN (0,1)),
    followup_date        DATE,
    referred_to_hospital BOOLEAN NOT NULL CHECK (referred_to_hospital IN (0,1)),
    remarks              VARCHAR(200)
);

CREATE TABLE USER_ACCOUNT (
    user_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    username     VARCHAR(30) NOT NULL UNIQUE,
    password     VARCHAR(100) NOT NULL,               -- hashed, never plain text
    full_name    VARCHAR(60) NOT NULL,
    role         VARCHAR(20) NOT NULL,                -- Patient, Nurse, Doctor, Administrator
    status       VARCHAR(15) NOT NULL,                -- Active, Inactive
    date_created DATE NOT NULL
);

CREATE TABLE MONTHLY_REPORT (
    report_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    report_month        VARCHAR(10) NOT NULL,
    report_year         INTEGER NOT NULL,
    total_visits        INTEGER NOT NULL,
    total_consultations INTEGER NOT NULL,
    total_first_aid     INTEGER NOT NULL,
    total_referrals     INTEGER NOT NULL,
    generated_by        INTEGER NOT NULL REFERENCES USER_ACCOUNT(user_id),
    date_generated      DATE NOT NULL
);
