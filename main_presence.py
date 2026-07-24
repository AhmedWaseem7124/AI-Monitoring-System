import os
import time
import cv2
from datetime import datetime

from app.config import load_config
from app.camera import Camera
from app.detector import PersonDetector
from app.database import EventDatabase
from app.notifier import EmailNotifier


EXIT_AFTER_SECONDS = 15
PROCESS_EVERY_SECONDS = 0.2


def main():
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

    camera.connect()

    person_inside = False
    last_seen_time = None

    print("[SYSTEM] Presence-based Enter/Exit Monitoring Started")
    cv2.namedWindow("Server Room Presence", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Server Room Presence", 900, 700)

    while True:
        ret, frame = camera.flush_and_read_latest(skip_frames=15)

        if not ret or frame is None:
            time.sleep(1)
            continue

        boxes = detector.detect_person(frame)

        person_detected = len(boxes) > 0
        now = datetime.now()

        if person_detected:
            last_seen_time = now

            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().tolist()

                cv2.rectangle(
                    frame,
                    (int(x1), int(y1)),
                    (int(x2), int(y2)),
                    (0, 255, 0),
                    2
                )

            if not person_inside:
                person_inside = True

                event_time = now.strftime("%Y-%m-%d %H:%M:%S")

                filename = now.strftime(
                    f"{captures_dir}/%Y%m%d_%H%M%S_PERSON_ENTERED.jpg"
                )

                cv2.imwrite(filename, frame)

                print(f"[EVENT] PERSON_ENTERED | {event_time}")

                email_sent = 0

                try:
                    notifier.send_alert(
                        image_path=filename,
                        event_time=event_time,
                        event_type="PERSON_ENTERED"
                    )
                    email_sent = 1

                except Exception as e:
                    print(f"[EMAIL ERROR] {e}")

                database.log_event(
                    event_time=event_time,
                    event_type="PERSON_ENTERED",
                    image_path=filename,
                    email_sent=email_sent
                )

        else:
            if person_inside and last_seen_time is not None:
                seconds_missing = (now - last_seen_time).seconds

                if seconds_missing >= EXIT_AFTER_SECONDS:
                    person_inside = False

                    # actual exit time = last time person was visible
                    exit_time = last_seen_time

                    event_time = exit_time.strftime("%Y-%m-%d %H:%M:%S")

                    filename = exit_time.strftime(
                        f"{captures_dir}/%Y%m%d_%H%M%S_PERSON_EXITED.jpg"
                    )

                    cv2.imwrite(filename, frame)

                    print(f"[EVENT] PERSON_EXITED | actual_exit_time={event_time}")

                    database.log_event(
                        event_time=event_time,
                        event_type="PERSON_EXITED",
                        image_path=filename,
                        email_sent=0
                    )

        status_text = "PERSON INSIDE" if person_inside else "NO PERSON"
        color = (0, 255, 0) if person_inside else (0, 0, 255)

        cv2.putText(
            frame,
            status_text,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            color,
            2
        )

        cv2.imshow("Server Room Presence", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        time.sleep(PROCESS_EVERY_SECONDS)

    camera.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
