# Server Room AI Monitoring System

An AI-powered real-time Server Room Monitoring System for Crescent Steel that performs employee recognition, access logging, intrusion detection, analytics, and automated reporting using CCTV footage.

---

# Features

## Real-Time Monitoring
- Live CCTV video streaming
- Person detection using YOLO
- Face recognition using InsightFace
- Automatic employee identification
- Unknown visitor detection
- Entry and exit detection
- Continuous background monitoring

---

## Employee Management

- Add new employees
- Capture face images directly from CCTV
- Automatic face dataset creation
- Employee profile management
- Department management
- Employee ID management
- Face gallery
- Employee activity history

---

## Event Logging

Automatically records:

- Person Entered
- Person Exited
- Authorized Access
- Unauthorized Access
- Unknown Visitors

Each event contains:

- Employee ID
- Employee Name
- Department
- Date & Time
- Snapshot
- Identity Status
- Email Status

---

## Dashboard

Displays

- Live camera feed
- Current room status
- Entries today
- Exits today
- Authorized entries
- Unknown entries
- First entry
- Last exit
- Recent events
- Quick navigation cards

---

## Analytics

Supports:

- Custom Date Range
- Multiple Day Analytics
- Hourly Entry Trend
- Hourly Exit Trend
- Identity Distribution
- Top Visitors
- Visitor Statistics

Charts:

- Line Chart
- Doughnut Chart
- Bar Chart

---

## Reports

Generate

- PDF Report
- Email Report

Report includes

- Summary
- Total Entries
- Total Exits
- Authorized Entries
- Unknown Entries
- Employee Details
- Department
- Complete Event History

---

## Email Alerts

Automatically sends email when

- Unknown person enters
- Unauthorized access detected

Email contains

- Snapshot
- Date
- Time
- Event
- Attached image

---

## Face Recognition

Powered by

- InsightFace
- Face Embeddings
- Cosine Similarity Matching

Supports

- Multiple registered employees
- Unknown face registration
- Face capture from CCTV
- Face database reload

---

## Technologies

### Backend

- Python
- Flask
- SQLite

### AI

- YOLO
- InsightFace
- OpenCV
- NumPy

### Frontend

- HTML
- CSS
- JavaScript
- Chart.js

### Reporting

- ReportLab

---

# Folder Structure

```
serverroom-ai/

│
├── server.py
├── database.py
├── face_auth.py
├── unknown_manager.py
├── config/
├── database/
├── templates/
├── static/
├── captures/
├── known_faces/
├── unknown_faces/
├── logs/
├── reports/
└── requirements.txt
```

---

# Database

## Employees

- Employee ID
- Employee Name
- Department
- Folder Name

## Events

- ID
- Event Time
- Event Type
- Person Name
- Image Path
- Email Sent

---

# Dashboard Pages

- Dashboard
- Employees
- Employee Profile
- Face Capture
- Analytics
- Reports
- Health Status

---

# AI Workflow

```
RTSP Camera
      │
      ▼
YOLO Person Detection
      │
      ▼
Presence Detection
      │
      ▼
Face Confirmation
      │
      ▼
InsightFace Recognition
      │
      ▼
Authorized / Unknown
      │
      ▼
Entry / Exit Logging
      │
      ▼
Dashboard Update
      │
      ▼
Analytics
      │
      ▼
PDF Reports
      │
      ▼
Email Alerts
```

---

# API Routes

```
/
```

Dashboard

```
/video_feed
```

Live stream

```
/employees
```

Employee Management

```
/employee/<id>
```

Employee Profile

```
/capture
```

Face Capture

```
/analytics
```

Analytics Dashboard

```
/events
```

Reports

```
/export/pdf
```

Export PDF

```
/send-report-email
```

Email Report

```
/health
```

System Health

---

# Current Status

## Completed

- Live Monitoring
- Face Recognition
- Unknown Detection
- Employee Management
- Face Capture
- Entry Detection
- Exit Detection
- Analytics
- Reports
- Email Alerts
- Dashboard
- Employee Profiles
- Event Search
- PDF Export
- Health Dashboard
- Multiple Date Analytics

---

# Pending

- Multiple Employees Simultaneously Inside Room
- Entry/Exit Tripwire Refinement
- Analytics Improvements
- Multi-Camera Support
- Role-Based Login
- Audit Logs
- Configuration Panel

---

# Deployment

Create virtual environment

```bash
python -m venv venv
```

Activate

```bash
source venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

Run

```bash
python server.py
```

Open

```
http://localhost:5000
```

---

# Environment Variables

```
CAMERA_URL=

SMTP_SERVER=
SMTP_PORT=
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_RECIPIENT=

SECRET_KEY=
```

---

# Future Enhancements

- Multiple cameras
- PPE Detection
- Attendance Reports
- SMS Alerts
- WhatsApp Notifications
- Visitor Approval System
- Mobile Dashboard
- Face Anti-Spoofing
- Liveness Detection
- Cloud Deployment

---

# Project

Developed for:

**Crescent Steel & Allied Products Ltd.**

Department:

**IT Department**

Purpose:

AI-powered Server Room Security, Access Monitoring, and Analytics Platform.

```
