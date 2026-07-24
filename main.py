import os
import time
import cv2
from datetime import datetime

from app.config import load_config
from app.camera import Camera
from app.detector import PersonDetector
from app.database import EventDatabase
from app.notifier import EmailNotifier


def main():
    config = load_config()

    captures_dir = config["storage"]["captures_dir"]
    os.makedirs(captures_dir, exist_ok=True)

    camera = Camera(config["camera"]["rtsp_url"])

    detector = PersonDetector(
        config["model"]["path"],
        config["model"]["confidence"]
    )

    database = EventDatabase(
        config["storage"]["database_path"]
    )

    notifier = EmailNotifier(
        config["smtp"]
    )

    cooldown = config["alert"]["cooldown_seconds"]
    last_detection_time = None

    camera.connect()

    print("[SYSTEM] Server Room AI started")

    while True:
        ret, frame = camera.read_frame()

        if not ret:
            time.sleep(1)
            continue

        boxes = detector.detect_person(frame)

        if len(boxes) > 0:
            now = datetime.now()

            if (
                last_detection_time is None
                or (now - last_detection_time).seconds > cooldown
            ):
                event_time = now.strftime("%Y-%m-%d %H:%M:%S")

                filename = now.strftime(
                    f"{captures_dir}/%Y%m%d_%H%M%S.jpg"
                )

                cv2.imwrite(filename, frame)

                print(f"[DETECTED] Snapshot saved: {filename}")

                email_sent = 0

                try:
                    notifier.send_alert(
                        image_path=filename,
                        event_time=event_time,
                        event_type="PERSON_DETECTED"
                    )
                    email_sent = 1

                except Exception as e:
                    print(f"[EMAIL ERROR] {e}")

                database.log_event(
                    event_time=event_time,
                    event_type="PERSON_DETECTED",
                    image_path=filename,
                    email_sent=email_sent
                )

                last_detection_time = now

        time.sleep(1)


if __name__ == "__main__":
    main()
