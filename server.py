from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)

import shutil
from werkzeug.utils import secure_filename
import numpy as np
import psutil
import os
import time
import cv2
import sqlite3
import threading

from app.unknown_manager import UnknownManager
from flask import Flask, render_template, Response, send_from_directory, request, send_file, jsonify, session, redirect
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from flask import send_from_directory
from datetime import datetime
from flask import Flask, render_template, Response

from app.config import load_config
from app.camera import Camera
from app.detector import PersonDetector
from app.database import EventDatabase
from app.notifier import EmailNotifier
from app.face_auth_insight import InsightFaceAuthenticator

app = Flask(
    __name__,
    template_folder="dashboard/templates",
    static_folder="dashboard/static"
)

app.secret_key = "crescent-ai-server-room-secret-2026"


# =========================
# GLOBAL STATE
# =========================

latest_frame = None
latest_frame_lock = threading.Lock()

ENTRY_EXIT_LINE_X = 455
DRAW_ENTRY_LINE = True

camera_status = "STARTING"
ai_status = "STARTING"
person_status = "NO PERSON"

stop_event = threading.Event()

inside_people = {}
inside_people_lock = threading.Lock()

EXIT_AFTER_SECONDS = 15
PROCESS_EVERY_SECONDS = 0.2
FACE_CONFIRM_SECONDS = 3
face_auth_global = None
capture_lock = threading.Lock()
capture_requests = {}

# Employee enrollment mode
enrollment_mode = False
current_enrollment_employee = None

def get_db_connection():
    config = load_config()
    db_path = config["storage"]["database_path"]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_employee_details_from_person(person_name):
    if not person_name:
        person_name = "UNKNOWN"

    if person_name.startswith("UNKNOWN"):
        return {
            "employee_id": "-",
            "display_name": person_name,
            "department": "-",
            "identity": "Unknown"
        }

    folder_name = person_name.lower()

    conn = get_db_connection()
    emp = conn.execute(
        """
        SELECT employee_id, employee_name, department
        FROM employees
        WHERE folder_name = ?
        """,
        (folder_name,)
    ).fetchone()
    conn.close()

    if emp:
        return {
            "employee_id": emp["employee_id"],
            "display_name": emp["employee_name"],
            "department": emp["department"],
            "identity": "Authorized"
        }

    return {
        "employee_id": "-",
        "display_name": person_name,
        "department": "-",
        "identity": "Authorized"
    }

def get_dashboard_data():
    today = datetime.now().strftime("%Y-%m-%d")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*) AS count FROM events
        WHERE event_type='PERSON_ENTERED'
        AND event_time LIKE ?
        """,
        (today + "%",)
    )
    entries_today = cursor.fetchone()["count"]

    cursor.execute(
        """
        SELECT COUNT(*) AS count FROM events
        WHERE event_type='PERSON_EXITED'
        AND event_time LIKE ?
        """,
        (today + "%",)
    )
    exits_today = cursor.fetchone()["count"]

    cursor.execute(
        """
        SELECT COUNT(*) AS count FROM events
        WHERE email_sent=1
        AND event_time LIKE ?
        """,
        (today + "%",)
    )
    emails_sent = cursor.fetchone()["count"]
    
    cursor.execute(
        """
        SELECT COUNT(*) AS count FROM events
        WHERE person_name != 'UNKNOWN'
        AND event_type='PERSON_ENTERED'
        AND event_time LIKE ?
        """,
        (today + "%",)
    )
    authorized_entries = cursor.fetchone()["count"]

    cursor.execute(
        """
        SELECT COUNT(*) AS count FROM events
        WHERE person_name = 'UNKNOWN'
        AND event_type='PERSON_ENTERED'
        AND event_time LIKE ?
        """,
        (today + "%",)
    )
    unknown_entries = cursor.fetchone()["count"]

    cursor.execute(
        """
        SELECT * FROM events
        ORDER BY id DESC
        LIMIT 10
        """
    )

    

    recent_events = cursor.fetchall()

    cursor.execute(
        """
        SELECT * FROM events
        ORDER BY id DESC
        LIMIT 1
        """
    )
    last_event = cursor.fetchone()

    cursor.execute(
        """
        SELECT MIN(event_time) AS first_entry
        FROM events
        WHERE event_type='PERSON_ENTERED'
        AND event_time LIKE ?
        """,
        (today + "%",)
    )
    first_entry = cursor.fetchone()["first_entry"]

    cursor.execute(
        """
        SELECT MAX(event_time) AS last_exit
        FROM events
        WHERE event_type='PERSON_EXITED'
        AND event_time LIKE ?
        """,
        (today + "%",)
    )
    last_exit = cursor.fetchone()["last_exit"]

    conn.close()

    enriched_recent_events = []

    for event in recent_events:
        event_dict = dict(event)
        emp_info = get_employee_details_from_person(event_dict.get("person_name"))

        event_dict["employee_id"] = emp_info["employee_id"]
        event_dict["display_name"] = emp_info["display_name"]
        event_dict["department"] = emp_info["department"]
        event_dict["identity"] = emp_info["identity"]

        enriched_recent_events.append(event_dict)

    return {
        "date": today,
        "entries_today": entries_today,
        "exits_today": exits_today,
        "emails_sent": emails_sent,
        "recent_events": enriched_recent_events,
        "last_event": last_event,
        "camera_status": camera_status,
        "ai_status": ai_status,
        "person_status": person_status,
        "authorized_entries": authorized_entries,
        "unknown_entries": unknown_entries,
        "first_entry": first_entry,
        "last_exit": last_exit
    }

def confirm_faces(camera, face_auth, unknown_manager, duration_seconds=3):
    start_time = time.time()

    known_names = []
    unknown_embeddings = []
    last_unknown_frame = None

    while time.time() - start_time < duration_seconds:
        ret, frame = camera.flush_and_read_latest(skip_frames=10)

        if not ret or frame is None:
            continue

        results = face_auth.recognize_all(frame)

        for result in results:
            name = result["name"]
            embedding = result["embedding"]

            if name == "UNKNOWN":
                unknown_embeddings.append(embedding)
                last_unknown_frame = frame.copy()
            else:
                known_names.append(name)

        time.sleep(0.3)

    # If known person detected in multiple frames, return known person only
    if known_names:
        final_names = []

        for name in known_names:
            if name not in final_names:
                final_names.append(name)

        return final_names

    # If no known person, decide unknown only once
    if unknown_embeddings:
        avg_embedding = sum(unknown_embeddings) / len(unknown_embeddings)
        avg_embedding = avg_embedding / np.linalg.norm(avg_embedding)

        unknown_result = unknown_manager.match_or_create(
            embedding=avg_embedding,
            snapshot_frame=last_unknown_frame
        )

        return [unknown_result["unknown_id"]]

    return ["UNKNOWN"]

def crop_largest_face(frame, face_auth):
    faces = face_auth.app.get(frame)

    if len(faces) == 0:
        return None, "No face detected"

    if len(faces) > 1:
        return None, "Multiple faces detected"

    face = faces[0]
    x1, y1, x2, y2 = face.bbox.astype(int)

    h, w = frame.shape[:2]

    # Add padding around face
    pad = 40
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(w, x2 + pad)
    y2 = min(h, y2 + pad)

    face_crop = frame[y1:y2, x1:x2]

    if face_crop.size == 0:
        return None, "Invalid face crop"

    face_width = x2 - x1
    face_height = y2 - y1

    if face_width < 80 or face_height < 80:
        return None, "Face too small"

    return face_crop, "OK"

def is_inside_server_room(box):
    x1, y1, x2, y2 = box.xyxy[0].cpu().tolist()

    # Use bottom-center of person box because feet/body position is better
    center_x = int((x1 + x2) / 2)
    bottom_y = int(y2)

    # Left side of line = inside server room
    return center_x < ENTRY_EXIT_LINE_X

def add_person_inside(person_name, entry_time):
    global inside_people

    with inside_people_lock:
        if person_name not in inside_people:
            inside_people[person_name] = {
                "entry_time": entry_time,
                "last_seen": entry_time
            }
            return True

        inside_people[person_name]["last_seen"] = entry_time
        return False


def update_person_seen(person_name, seen_time):
    global inside_people

    with inside_people_lock:
        if person_name in inside_people:
            inside_people[person_name]["last_seen"] = seen_time


def remove_person_inside(person_name):
    global inside_people

    with inside_people_lock:
        if person_name in inside_people:
            del inside_people[person_name]


def get_inside_people():
    with inside_people_lock:
        return dict(inside_people)

def ai_worker():
    global latest_frame
    global camera_status
    global ai_status
    global person_status
    global face_auth_global
    global enrollment_mode
    global current_enrollment_employee

    config = load_config()

    captures_dir = config["storage"]["captures_dir"]
    os.makedirs(captures_dir, exist_ok=True)

    camera = Camera(config["camera"]["rtsp_url"])

    detector = PersonDetector(
        config["model"]["path"],
        config["model"]["confidence"]
    )

    database = EventDatabase(config["storage"]["database_path"])
    notifier = EmailNotifier(config["smtp"])

    face_auth = InsightFaceAuthenticator("known_faces")
    face_auth_global = face_auth

    unknown_manager = UnknownManager("unknown_faces")

    last_seen_time = None
    current_person_names = []

    try:
        camera.connect()
        camera_status = "ONLINE"
        ai_status = "RUNNING"

    except Exception as e:
        camera_status = "OFFLINE"
        ai_status = "ERROR"
        print(f"[CAMERA ERROR] {e}")
        return

    print("[SYSTEM] AI Worker Started")

    while not stop_event.is_set():

        ret, frame = camera.flush_and_read_latest(skip_frames=15)

        if not ret or frame is None:
            camera_status = "OFFLINE"
            time.sleep(1)
            continue

        camera_status = "ONLINE"

        # ==========================================
        # EMPLOYEE ENROLLMENT MODE
        # ==========================================
        if enrollment_mode:

            display_frame = frame.copy()

            cv2.putText(
                display_frame,
                "ENROLLMENT MODE - AI PAUSED",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 255),
                2
            )

            with latest_frame_lock:
                latest_frame = display_frame.copy()

            with capture_lock:
                active_captures = {
                    emp_id: req.copy()
                    for emp_id, req in capture_requests.items()
                    if req.get("active")
                }

            for emp_id, req in active_captures.items():

                # Finish by target image count
                if req["saved"] >= req["target"]:
                    with capture_lock:
                        capture_requests[emp_id]["active"] = False
                        capture_requests[emp_id]["completed"] = True
                        capture_requests[emp_id]["message"] = "Enrollment complete"

                    enrollment_mode = False
                    current_enrollment_employee = None

                    if face_auth_global is not None:
                        face_auth_global.reload_known_faces()

                    print("[ENROLLMENT] Completed successfully")
                    continue

                last_saved = req.get("last_saved", 0)

                # Capture every 0.8 seconds
                if time.time() - last_saved < 0.8:
                    continue

                conn = get_db_connection()
                employee = conn.execute(
                    """
                    SELECT *
                    FROM employees
                    WHERE id = ?
                    """,
                    (emp_id,)
                ).fetchone()
                conn.close()

                if not employee:
                    continue

                folder_name = employee["folder_name"]
                folder_path = os.path.join("known_faces", folder_name)
                os.makedirs(folder_path, exist_ok=True)

                existing_nums = []

                for f in os.listdir(folder_path):
                    if f.lower().endswith((".jpg", ".jpeg", ".png")) and f.lower().startswith("img"):
                        try:
                            num = int(f.split(".")[0].replace("img", ""))
                            existing_nums.append(num)
                        except:
                            pass

                next_num = max(existing_nums) + 1 if existing_nums else 1

                filename = f"img{next_num}.jpg"
                save_path = os.path.join(folder_path, filename)

                face_crop, reason = crop_largest_face(frame, face_auth)

                if face_crop is None:
                    print(f"[CAPTURE] Skipped: {reason}")
                    continue

                cv2.imwrite(save_path, face_crop)

                with capture_lock:
                    capture_requests[emp_id]["saved"] += 1
                    capture_requests[emp_id]["last_saved"] = time.time()

                print(f"[CAPTURE] Saved {save_path}")

            time.sleep(0.02)
            continue

        # ==========================================
        # NORMAL AI PIPELINE
        # ==========================================

        all_boxes = detector.detect_person(frame)

        boxes = [box for box in all_boxes if is_inside_server_room(box)]

        person_detected = len(boxes) > 0
        now = datetime.now()

        display_frame = frame.copy()

        if DRAW_ENTRY_LINE:
            h, w = display_frame.shape[:2]

        cv2.line(
            display_frame,
            (ENTRY_EXIT_LINE_X, 0),
            (ENTRY_EXIT_LINE_X, h),
            (0, 255, 255),
            3
        )

        cv2.putText(
            display_frame,
            "SERVER ROOM SIDE",
            (20, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2
        )

        cv2.putText(
            display_frame,
            "OUTSIDE",
            (ENTRY_EXIT_LINE_X + 10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2
        )

        # Draw all detected people
        for box in all_boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().tolist()

            inside = is_inside_server_room(box)

            color = (0, 255, 0) if inside else (0, 0, 255)
            label = "INSIDE" if inside else "OUTSIDE"

            cv2.rectangle(
                display_frame,
                (int(x1), int(y1)),
                (int(x2), int(y2)),
                color,
                2
            )

            cv2.putText(
                display_frame,
                label,
                (int(x1), int(y1) - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2
            )
        # =========================
        # PERSON PRESENT
        # =========================

        if person_detected:
            last_seen_time = now
            person_status = "PERSON INSIDE"

            print("[FACE] Confirming face for 3 seconds...")

            current_person_names = confirm_faces(
                camera,
                face_auth,
                unknown_manager,
                FACE_CONFIRM_SECONDS
            )

            print(f"[FACE] Confirmed persons: {current_person_names}")

            event_time = now.strftime("%Y-%m-%d %H:%M:%S")

            filename = now.strftime(
                f"{captures_dir}/%Y%m%d_%H%M%S_PERSON_ENTERED.jpg"
            )

            cv2.imwrite(filename, display_frame)

            for person_name in current_person_names:

                is_new_entry = add_person_inside(person_name, now)

                if not is_new_entry:
                    update_person_seen(person_name, now)
                    continue

                    email_sent = 0

                    if person_name.startswith("UNKNOWN"):
                        try:
                            notifier.send_alert(
                                image_path=filename,
                                event_time=event_time,
                                event_type=f"{person_name}_ENTERED"
                            )

                            email_sent = 1

                        except Exception as e:
                            print(f"[EMAIL ERROR] {e}")

                    else:
                        print(f"[ACCESS GRANTED] {person_name}")

                    database.log_event(
                        event_time=event_time,
                        event_type="PERSON_ENTERED",
                        image_path=filename,
                        email_sent=email_sent,
                        person_name=person_name
                    )

                print(
                    f"[EVENT] PERSON_ENTERED | {current_person_names} | {event_time}"
                )

        # =========================
        # NO PERSON PRESENT
        # =========================

        else:
            inside_snapshot = get_inside_people()

            if len(inside_snapshot) == 0:
                person_status = "NO PERSON"

            for person_name, info in inside_snapshot.items():
                seconds_missing = (now - info["last_seen"]).seconds

                if seconds_missing >= EXIT_AFTER_SECONDS:
                    exit_time = info["last_seen"]
                    event_time = exit_time.strftime("%Y-%m-%d %H:%M:%S")

                    filename = exit_time.strftime(
                        f"{captures_dir}/%Y%m%d_%H%M%S_PERSON_EXITED.jpg"
                    )

                    cv2.imwrite(filename, display_frame)

                    database.log_event(
                        event_time=event_time,
                        event_type="PERSON_EXITED",
                        image_path=filename,
                        email_sent=0,
                        person_name=person_name
                    )

                    remove_person_inside(person_name)

                    print(
                        f"[EVENT] PERSON_EXITED | {person_name} | actual_exit_time={event_time}"
                    )

        # =========================
        # DISPLAY STATUS ON FRAME
        # =========================

        inside_count = len(get_inside_people())

        status_text = f"INSIDE: {inside_count}" if inside_count > 0 else "NO PERSON"

        cv2.putText(
            display_frame,
            status_text,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0) if inside_count > 0 else (0, 0, 255),
            2
        )

        with latest_frame_lock:
            latest_frame = display_frame.copy()

        time.sleep(PROCESS_EVERY_SECONDS)

    camera.release()

def generate_video():
    global latest_frame

    while True:
        with latest_frame_lock:
            frame = None if latest_frame is None else latest_frame.copy()

        if frame is None:
            time.sleep(0.2)
            continue

        ret, buffer = cv2.imencode(".jpg", frame)

        if not ret:
            continue

        frame_bytes = buffer.tobytes()

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )

        time.sleep(0.1)

def search_events(start_date=None,end_date=None,event_type=None,person_name=None,identity=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM events WHERE 1=1"
    params = []

    if start_date:
        query += " AND event_time >= ?"
        params.append(start_date + " 00:00:00")

    if end_date:
        query += " AND event_time <= ?"
        params.append(end_date + " 23:59:59")

    if event_type and event_type != "ALL":
        query += " AND event_type = ?"
        params.append(event_type)
   
    # Person filter
    if person_name and person_name != "ALL":
        query += " AND person_name = ?"
        params.append(person_name)

# Identity filter
    if identity == "AUTHORIZED":
        query += " AND person_name NOT LIKE 'UNKNOWN%'"

    elif identity == "UNKNOWN":
        query += " AND person_name LIKE 'UNKNOWN%'"
        query += " ORDER BY id DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    conn.close()
    return rows

def build_pdf_report(rows, start_date=None, end_date=None, event_type="ALL", person_name="ALL", identity="ALL"):
    buffer = BytesIO()

    events = [enrich_event_with_employee(row) for row in rows]
    summary = build_report_summary(events)

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()
    story = []

    title = Paragraph(
        "<b>Crescent Steel & Allied Products Ltd.</b>",
        styles["Title"]
    )

    subtitle = Paragraph(
        "AI Server Room Monitoring Report",
        styles["Heading2"]
    )

    period = Paragraph(
        f"""
        <b>Report Period:</b> {start_date or 'All'} to {end_date or 'All'}<br/>
        <b>Event Type:</b> {event_type}<br/>
        <b>Person:</b> {person_name}<br/>
        <b>Identity:</b> {identity}<br/>
        <b>Generated On:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """,
        styles["Normal"]
    )

    story.append(title)
    story.append(subtitle)
    story.append(Spacer(1, 12))
    story.append(period)
    story.append(Spacer(1, 20))

    story.append(Paragraph("<b>Executive Summary</b>", styles["Heading2"]))

    summary_data = [
        ["Total Events", summary["total_events"], "Total Entries", summary["total_entries"]],
        ["Total Exits", summary["total_exits"], "Authorized Entries", summary["authorized_entries"]],
        ["Unknown Entries", summary["unknown_entries"], "Email Alerts Sent", summary["emails_sent"]],
        ["Most Frequent Visitor", summary["most_frequent_visitor"], "Latest Unknown Visitor", summary["latest_unknown"]],
        ["First Entry", summary["first_entry"], "Last Exit", summary["last_exit"]],
    ]

    summary_table = Table(summary_data, colWidths=[160, 160, 160, 160])

    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(summary_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("<b>Detailed Event Log</b>", styles["Heading2"]))

    table_data = [
        [
            "S.No",
            "Date & Time",
            "Employee ID",
            "Employee Name",
            "Department",
            "Identity",
            "Event",
            "Email"
        ]
    ]

    for idx, event in enumerate(events, start=1):
        event_label = "Entry" if event["event_type"] == "PERSON_ENTERED" else "Exit"

        table_data.append([
            idx,
            event["event_time"],
            event["employee_id"],
            event["employee_name"],
            event["department"],
            event["identity"],
            event_label,
            "Yes" if event["email_sent"] == 1 else "No"
        ])

    event_table = Table(
        table_data,
        repeatRows=1,
        colWidths=[40, 120, 90, 140, 100, 90, 70, 60]
    )

    event_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))

    story.append(event_table)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(30, 18, "AI Server Room Monitoring System | Crescent Steel & Allied Products Ltd.")
        canvas.drawRightString(810, 18, f"Page {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)

    buffer.seek(0)
    return buffer

def enrich_event_with_employee(event):
    person_name = event["person_name"] or "UNKNOWN"
    enriched = dict(event)

    if person_name.startswith("UNKNOWN"):
        enriched["employee_id"] = "-"
        enriched["employee_name"] = person_name
        enriched["department"] = "-"
        enriched["identity"] = "Unknown"
        return enriched

    folder_name = person_name.lower()

    conn = get_db_connection()
    employee = conn.execute(
        """
        SELECT employee_id, employee_name, department
        FROM employees
        WHERE folder_name = ?
        """,
        (folder_name,)
    ).fetchone()
    conn.close()

    if employee:
        enriched["employee_id"] = employee["employee_id"]
        enriched["employee_name"] = employee["employee_name"]
        enriched["department"] = employee["department"]
        enriched["identity"] = "Authorized"
    else:
        enriched["employee_id"] = "-"
        enriched["employee_name"] = person_name
        enriched["department"] = "-"
        enriched["identity"] = "Authorized"

    return enriched


def build_report_summary(events):
    entries = [e for e in events if e["event_type"] == "PERSON_ENTERED"]
    exits = [e for e in events if e["event_type"] == "PERSON_EXITED"]

    authorized_entries = [
        e for e in entries
        if not (e["person_name"] or "").startswith("UNKNOWN")
    ]

    unknown_entries = [
        e for e in entries
        if (e["person_name"] or "").startswith("UNKNOWN")
    ]

    emails_sent = [
        e for e in events
        if e["email_sent"] == 1
    ]

    visitor_counts = {}

    for e in entries:
        name = e["person_name"] or "UNKNOWN"
        visitor_counts[name] = visitor_counts.get(name, 0) + 1

    most_frequent_visitor = "-"

    if visitor_counts:
        most_frequent_visitor = max(visitor_counts, key=visitor_counts.get)

    latest_unknown = "-"

    for e in events:
        if (e["person_name"] or "").startswith("UNKNOWN"):
            latest_unknown = e["person_name"]
            break

    first_entry = entries[-1]["event_time"] if entries else "-"
    last_exit = exits[0]["event_time"] if exits else "-"

    return {
        "total_events": len(events),
        "total_entries": len(entries),
        "total_exits": len(exits),
        "authorized_entries": len(authorized_entries),
        "unknown_entries": len(unknown_entries),
        "emails_sent": len(emails_sent),
        "most_frequent_visitor": most_frequent_visitor,
        "latest_unknown": latest_unknown,
        "first_entry": first_entry,
        "last_exit": last_exit
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == "admin" and password == "admin123":
            session["logged_in"] = True
            return redirect("/")
        else:
            error = "Invalid username or password"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.before_request
def require_login():
    allowed_paths = ["/login"]

    if request.path.startswith("/static"):
        return

    if request.path in allowed_paths:
        return

    if not session.get("logged_in"):
        return redirect("/login")


@app.route("/")
def index():
    data = get_dashboard_data()
    return render_template("index.html", data=data)


@app.route("/video_feed")
def video_feed():
    return Response(
        generate_video(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )
@app.route("/captures/<path:filename>")
def captures(filename):
    return send_from_directory("captures", filename)

@app.route("/events")
def events():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    event_type = request.args.get("event_type", "ALL")
    person_name = request.args.get("person_name", "ALL")
    identity = request.args.get("identity", "ALL")

    rows = search_events(
        start_date,
        end_date,
        event_type,
        person_name,
        identity
    )

    conn = get_db_connection()

    people = conn.execute(
        """
        SELECT employee_name, folder_name
        FROM employees
        ORDER BY employee_name        """
    ).fetchall()

    conn.close()

    return render_template(
        "events.html",
        events=rows,
        start_date=start_date,
        end_date=end_date,
        event_type=event_type,
        person_name=person_name,
        identity=identity,
        people=people
    )

@app.route("/export/pdf")
def export_pdf():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    event_type = request.args.get("event_type", "ALL")
    person_name = request.args.get("person_name", "ALL")
    identity = request.args.get("identity", "ALL")

    rows = search_events(
        start_date,
        end_date,
        event_type,
        person_name,
        identity
    )

    buffer = build_pdf_report(
        rows,
        start_date,
        end_date,
        event_type,
        person_name,
        identity
    )

    return send_file(
        buffer,
        as_attachment=True,
        download_name="serverroom_ai_report.pdf",
        mimetype="application/pdf"
    )

@app.route("/send-report-email")
def send_report_email():
    config = load_config()

    recipient_email = request.args.get("recipient_email")
    custom_email = request.args.get("custom_email")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    event_type = request.args.get("event_type", "ALL")
    person_name = request.args.get("person_name", "ALL")
    identity = request.args.get("identity", "ALL")

    rows = search_events(
        start_date,
        end_date,
        event_type,
        person_name,
        identity
    )

    summary_events = [enrich_event_with_employee(row) for row in rows]
    summary = build_report_summary(summary_events)

    buffer = build_pdf_report(
        rows,
        start_date,
        end_date,
        event_type,
        person_name,
        identity
    )

    pdf_bytes = buffer.getvalue()

    notifier = EmailNotifier(config["smtp"])

    final_recipient = custom_email if custom_email else recipient_email

    if not final_recipient:
        final_recipient = config["smtp"]["recipient"]

    subject = "[AI REPORT] Server Room Monitoring Report"

    body = f"""
Dear Recipient,

Please find attached the AI Server Room Monitoring Report.

Report Summary
-----------------------
Total Events: {summary['total_events']}
Total Entries: {summary['total_entries']}
Total Exits: {summary['total_exits']}
Authorized Entries: {summary['authorized_entries']}
Unknown Entries: {summary['unknown_entries']}
Email Alerts Sent: {summary['emails_sent']}

Reporting Period:
{start_date or 'All'} to {end_date or 'All'}

Filters Applied:
Event Type: {event_type}
Person: {person_name}
Identity: {identity}

This report was generated automatically by the AI Server Room Monitoring System.

Regards,
AI Server Room Monitoring System
Crescent Steel & Allied Products Ltd.
"""

    notifier.send_email_with_attachment_to(
        recipient=final_recipient,
        subject=subject,
        body=body,
        attachment_bytes=pdf_bytes,
        filename="serverroom_ai_report.pdf"
    )

    return f"Report sent successfully to {final_recipient}." 


@app.route("/health")
def health():
    disk = psutil.disk_usage("/")
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=1)

    health_data = {
        "cpu_percent": cpu_percent,
        "memory_total": round(memory.total / (1024 ** 3), 2),
        "memory_used": round(memory.used / (1024 ** 3), 2),
        "memory_percent": memory.percent,
        "disk_total": round(disk.total / (1024 ** 3), 2),
        "disk_used": round(disk.used / (1024 ** 3), 2),
        "disk_percent": disk.percent,
        "camera_status": camera_status,
        "ai_status": ai_status,
        "person_status": person_status
    }

    return render_template("health.html", health=health_data)

@app.route("/api/dashboard")
def api_dashboard():
    data = get_dashboard_data()

    recent_events = []

    for event in data["recent_events"]:
        recent_events.append({
            "id": event["id"],
            "event_time": event["event_time"],
            "event_type": event["event_type"],
            "person_name": event["person_name"],
            "employee_id": event.get("employee_id", "-"),
            "display_name": event.get("display_name", event["person_name"]),
            "department": event.get("department", "-"),
            "identity": event.get("identity", "Unknown" if event["person_name"].startswith("UNKNOWN") else "Authorized"),
            "image_path": event["image_path"],
            "email_sent": event["email_sent"]
        })


    last_event = None

    if data["last_event"]:
        last_event = {
            "id": data["last_event"]["id"],
            "event_time": data["last_event"]["event_time"],
            "event_type": data["last_event"]["event_type"],
            "person_name": data["last_event"]["person_name"],
            "image_path": data["last_event"]["image_path"],
            "email_sent": data["last_event"]["email_sent"]
        }

    return jsonify({
        "date": data["date"],
        "entries_today": data["entries_today"],
        "exits_today": data["exits_today"],
        "emails_sent": data["emails_sent"],
        "camera_status": data["camera_status"],
        "ai_status": data["ai_status"],
        "person_status": data["person_status"],
        "last_event": last_event,
        "recent_events": recent_events,
        "first_entry": data["first_entry"],
        "last_exit": data["last_exit"],
        "authorized_entries": data["authorized_entries"],
        "unknown_entries": data["unknown_entries"]
    })

@app.route("/analytics")
def analytics():
    start_date = request.args.get("start_date", datetime.now().strftime("%Y-%m-%d"))
    end_date = request.args.get("end_date", datetime.now().strftime("%Y-%m-%d"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) AS count FROM events
        WHERE event_type='PERSON_ENTERED'
        AND  date(event_time) BETWEEN ? AND ?
    """, (start_date, end_date))
    total_entries = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*) AS count FROM events
        WHERE event_type='PERSON_EXITED'
        AND date(event_time) BETWEEN ? AND ?
    """, (start_date, end_date))
    total_exits = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*) AS count FROM events
        WHERE person_name LIKE 'UNKNOWN%'
        AND event_type='PERSON_ENTERED'
        AND date(event_time) BETWEEN ? AND ?
    """, (start_date, end_date))
    unknown_entries = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT COUNT(*) AS count FROM events
        WHERE person_name NOT LIKE 'UNKNOWN%'
        AND event_type='PERSON_ENTERED'
        AND date(event_time) BETWEEN ? AND ?
    """, (start_date, end_date))
    authorized_entries = cursor.fetchone()["count"]

    cursor.execute("""
        SELECT person_name, COUNT(*) AS visits
        FROM events
        WHERE event_type='PERSON_ENTERED'
        AND date(event_time) BETWEEN ? AND ?
        GROUP BY person_name
        ORDER BY visits DESC
        LIMIT 6
    """, (start_date, end_date))
    top_visitors = cursor.fetchall()

    cursor.execute("""
        SELECT person_name, event_time
        FROM events
        WHERE person_name LIKE 'UNKNOWN%'
        AND date(event_time) BETWEEN ? AND ?
        ORDER BY id DESC
        LIMIT 1
    """, (start_date, end_date))
    latest_unknown = cursor.fetchone()

    hours = [f"{h:02d}" for h in range(24)]
    entries_by_hour = []
    exits_by_hour = []

    for h in hours:
        cursor.execute("""
            SELECT COUNT(*) AS count FROM events
            WHERE event_type='PERSON_ENTERED'
            AND substr(event_time, 12, 2)=?
            AND date(event_time) BETWEEN ? AND ?
        """, (h, start_date, end_date))
        entries_by_hour.append(cursor.fetchone()["count"])

        cursor.execute("""
            SELECT COUNT(*) AS count FROM events
            WHERE event_type='PERSON_EXITED'
            AND substr(event_time, 12, 2)=?
            AND date(event_time) BETWEEN ? AND ?
        """, (h, start_date, end_date))
        exits_by_hour.append(cursor.fetchone()["count"])

    conn.close()

    return render_template(
        "analytics.html",
        start_date=start_date,
        end_date=end_date,
        selected_date=f"{start_date} to {end_date}",
        total_entries=total_entries,
        total_exits=total_exits,
        unknown_entries=unknown_entries,
        authorized_entries=authorized_entries,
        top_visitors=top_visitors,
        latest_unknown=latest_unknown,
        hours=hours,
        entries_by_hour=entries_by_hour,
        exits_by_hour=exits_by_hour
    )

@app.route("/employees")
def employees():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM employees
        ORDER BY employee_name
    """)

    db_employees = cursor.fetchall()

    employees_data = []

    for emp in db_employees:

        folder = emp["folder_name"]
        folder_path = os.path.join("known_faces", folder)

        image_count = 0
        preview = []

        if os.path.exists(folder_path):

            files = [
                f for f in os.listdir(folder_path)
                if f.lower().endswith((".jpg", ".jpeg", ".png"))
            ]

            image_count = len(files)
            preview = files[:3]

        employees_data.append({

            "id": emp["id"],
            "employee_name": emp["employee_name"],
            "folder_name": folder,
            "employee_id": emp["employee_id"],
            "department": emp["department"],
            "designation": emp["designation"],
            "email": emp["email"],
            "phone": emp["phone"],
            "status": emp["status"],
            "image_count": image_count,
            "preview": preview

        })

    conn.close()

    return render_template(
        "employees.html",
        employees=employees_data
    )


@app.route("/employees/add", methods=["POST"])
def add_employee():

    employee_name = request.form["employee_name"].strip()

    folder_name = employee_name.lower().replace(" ", "_")

    employee_id = request.form["employee_id"]
    department = request.form["department"]
    designation = request.form["designation"]
    email = request.form["email"]
    phone = request.form["phone"]

    files = request.files.getlist("images")

    folder = os.path.join("known_faces", folder_name)
    os.makedirs(folder, exist_ok=True)

    existing = len(os.listdir(folder))

    for file in files:

        if file.filename:

            ext = file.filename.rsplit(".",1)[1].lower()

            filename = f"img{existing+1}.{ext}"

            file.save(
                os.path.join(folder, filename)
            )

            existing += 1

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""

        INSERT INTO employees(

            employee_name,
            folder_name,
            employee_id,
            department,
            designation,
            email,
            phone,
            created_at

        )

        VALUES(?,?,?,?,?,?,?,?)

    """,(

        employee_name,
        folder_name,
        employee_id,
        department,
        designation,
        email,
        phone,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ))

    conn.commit()
    conn.close()

    return redirect("/employees")

@app.route("/employees/delete/<employee>")
def delete_employee(employee):
    global face_auth_global

    emp_dir = os.path.join("known_faces", employee)

    if os.path.exists(emp_dir):
        shutil.rmtree(emp_dir)

    conn = get_db_connection()
    conn.execute(
        "DELETE FROM employees WHERE folder_name = ?",
        (employee,)
    )
    conn.commit()
    conn.close()

    if face_auth_global is not None:
        face_auth_global.reload_known_faces()

    return redirect("/employees")

@app.route("/employee/<int:employee_id>/delete-image/<path:filename>")
def delete_employee_image(employee_id, filename):
    global face_auth_global

    conn = get_db_connection()
    employee = conn.execute(
        "SELECT * FROM employees WHERE id = ?",
        (employee_id,)
    ).fetchone()
    conn.close()

    if not employee:
        return "Employee not found"

    image_path = os.path.join(
        "known_faces",
        employee["folder_name"],
        filename
    )

    if os.path.exists(image_path):
        os.remove(image_path)
        print(f"[EMPLOYEE] Deleted image: {image_path}")

    if face_auth_global is not None:
        face_auth_global.reload_known_faces()

    return redirect(f"/employee/{employee_id}")

@app.route("/employee/<int:employee_id>/edit", methods=["GET", "POST"])
def edit_employee(employee_id):
    global face_auth_global

    conn = get_db_connection()

    employee = conn.execute(
        "SELECT * FROM employees WHERE id = ?",
        (employee_id,)
    ).fetchone()

    if not employee:
        conn.close()
        return "Employee not found"

    if request.method == "POST":
        employee_name = request.form.get("employee_name", "").strip()
        employee_code = request.form.get("employee_id", "").strip()
        department = request.form.get("department", "").strip()
        designation = request.form.get("designation", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        status = request.form.get("status", "ACTIVE")

        old_folder = employee["folder_name"]
        new_folder = employee_name.lower().replace(" ", "_")

        old_path = os.path.join("known_faces", old_folder)
        new_path = os.path.join("known_faces", new_folder)

        if old_folder != new_folder and os.path.exists(old_path):
            os.rename(old_path, new_path)

        conn.execute(
            """
            UPDATE employees
            SET employee_name = ?,
                folder_name = ?,
                employee_id = ?,
                department = ?,
                designation = ?,
                email = ?,
                phone = ?,
                status = ?
            WHERE id = ?
            """,
            (
                employee_name,
                new_folder,
                employee_code,
                department,
                designation,
                email,
                phone,
                status,
                employee_id
            )
        )

        conn.commit()
        conn.close()

        if face_auth_global is not None:
            face_auth_global.reload_known_faces()

        return redirect(f"/employee/{employee_id}")

    conn.close()

    return render_template(
        "employee_edit.html",
        employee=employee
    )

@app.route("/known-face/<employee>/<filename>")
def known_face(employee, filename):
    return send_from_directory(
        os.path.join("known_faces", employee),
        filename
    )

@app.route("/employee/<int:employee_id>")
def employee_profile(employee_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    employee = cursor.execute(
        """
        SELECT *
        FROM employees
        WHERE id = ?
        """,
        (employee_id,)
    ).fetchone()

    if not employee:
        conn.close()
        return "Employee not found"

    folder_name = employee["folder_name"]
    folder_path = os.path.join("known_faces", folder_name)

    images = []

    if os.path.exists(folder_path):
        images = [
            f for f in os.listdir(folder_path)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]

    person_name = employee["folder_name"].upper()

    visits = cursor.execute(
        """
        SELECT *
        FROM events
        WHERE person_name = ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (person_name,)
    ).fetchall()

    total_entries = cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM events
        WHERE person_name = ?
        AND event_type='PERSON_ENTERED'
        """,
        (person_name,)
    ).fetchone()["count"]

    total_exits = cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM events
        WHERE person_name = ?
        AND event_type='PERSON_EXITED'
        """,
        (person_name,)
    ).fetchone()["count"]

    last_seen = cursor.execute(
        """
        SELECT MAX(event_time) AS last_seen
        FROM events
        WHERE person_name = ?
        """,
        (person_name,)
    ).fetchone()["last_seen"]

    conn.close()

    return render_template(
        "employee_profile.html",
        employee=employee,
        images=images,
        visits=visits,
        total_entries=total_entries,
        total_exits=total_exits,
        last_seen=last_seen
    )

@app.route("/employees/reload-faces")
def reload_faces():
    global face_auth_global

    if face_auth_global is None:
        return "Face engine not ready yet"

    face_auth_global.reload_known_faces()

    return redirect("/employees")

@app.route("/employee/<int:employee_id>/upload", methods=["GET", "POST"])
def upload_employee_images(employee_id):
    global face_auth_global

    conn = get_db_connection()
    employee = conn.execute(
        """
        SELECT *
        FROM employees
        WHERE id = ?
        """,
        (employee_id,)
    ).fetchone()

    if not employee:
        conn.close()
        return "Employee not found"

    folder_name = employee["folder_name"]
    folder_path = os.path.join("known_faces", folder_name)
    os.makedirs(folder_path, exist_ok=True)

    if request.method == "POST":
        files = request.files.getlist("images")

        existing_images = [
            f for f in os.listdir(folder_path)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]

        count = len(existing_images)

        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)

                if "." not in filename:
                    continue

                ext = filename.rsplit(".", 1)[-1].lower()

                if ext not in ["jpg", "jpeg", "png"]:
                    continue

                count += 1
                save_name = f"img{count}.{ext}"

                file.save(
                    os.path.join(folder_path, save_name)
                )

        if face_auth_global is not None:
            face_auth_global.reload_known_faces()

        conn.close()
        return redirect(f"/employee/{employee_id}")

    conn.close()

    return render_template(
        "employee_upload.html",
        employee=employee
    )

@app.route("/employee/<int:employee_id>/capture")
def capture_employee_page(employee_id):
    conn = get_db_connection()

    employee = conn.execute(
        """
        SELECT *
        FROM employees
        WHERE id = ?
        """,
        (employee_id,)
    ).fetchone()

    conn.close()

    if not employee:
        return "Employee not found"

    return render_template(
        "employee_capture.html",
        employee=employee
    )


@app.route("/employee/<int:employee_id>/start-capture")
def start_employee_capture(employee_id):

    global enrollment_mode
    global current_enrollment_employee

    with capture_lock:

        capture_requests[employee_id] = {

            "active": True,
            "saved": 0,
            "target": 12,
            "started_at": time.time(),
            "last_saved": 0

        }

    enrollment_mode = True
    current_enrollment_employee = employee_id

    print(f"[ENROLLMENT] Started for employee {employee_id}")

    return redirect(f"/employee/{employee_id}/capture")

@app.route("/employee/<int:employee_id>/capture-status")
def employee_capture_status(employee_id):
    with capture_lock:
        req = capture_requests.get(employee_id, {
            "active": False,
            "saved": 0,
            "target": 10,
            "started_at": None
        })

    elapsed = 0

    if req.get("started_at"):
        elapsed = int(time.time() - req["started_at"])

    return jsonify({
        "completed": req.get("completed", False),
        "message": req.get("message", "Ready"),
        "active": req.get("active", False),
        "saved": req.get("saved", 0),
        "target": req.get("target", 10),
        "elapsed": elapsed
    })

@app.route("/employee/<int:employee_id>/stop-capture")
def stop_employee_capture(employee_id):
    global enrollment_mode
    global current_enrollment_employee

    with capture_lock:
        if employee_id in capture_requests:
            capture_requests[employee_id]["active"] = False
            capture_requests[employee_id]["completed"] = False
            capture_requests[employee_id]["message"] = "Capture stopped manually"

    enrollment_mode = False
    current_enrollment_employee = None

    print(f"[ENROLLMENT] Stopped manually for employee {employee_id}")

    return redirect(f"/employee/{employee_id}")

if __name__ == "__main__":
    worker_thread = threading.Thread(target=ai_worker, daemon=True)
    worker_thread.start()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True
    )
