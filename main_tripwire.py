import os
import time
import cv2
from datetime import datetime

from app.config import load_config
from app.camera import Camera
from app.tracker import PersonTracker
from app.database import EventDatabase
from app.notifier import EmailNotifier


# =========================
# TRIPWIRE CONFIG
# =========================
LINE_X = 390
LINE_Y1 = 40
LINE_Y2 = 560

# Door/right side = OUTSIDE
# Room/left side = INSIDE


def get_side(center_x):
    if center_x > LINE_X:
        return "OUTSIDE"
    return "INSIDE"


def main():
    config = load_config()

    captures_dir = config["storage"]["captures_dir"]
    os.makedirs(captures_dir, exist_ok=True)

    camera = Camera(config["camera"]["rtsp_url"])

    tracker = PersonTracker(
        config["model"]["path"],
        config["model"]["confidence"]
    )

    database = EventDatabase(config["storage"]["database_path"])
    notifier = EmailNotifier(config["smtp"])

    camera.connect()

    last_side = {}
    last_event_time = {}

    event_cooldown = 10

    print("[SYSTEM] Tripwire Monitoring Started")
    print("[INFO] Right side of line = OUTSIDE")
    print("[INFO] Left side of line  = INSIDE")

    while True:
        # =========================
        # FLUSH OLD BUFFERED FRAMES
        # =========================
        frame = None
        ret = False

        for _ in range(5):
            ret, frame = camera.read_frame()

        if not ret or frame is None:
            time.sleep(0.2)
            continue

        persons = tracker.track_persons(frame)

        # draw tripwire line
        cv2.line(
            frame,
            (LINE_X, LINE_Y1),
            (LINE_X, LINE_Y2),
            (0, 255, 255),
            2
        )

        cv2.putText(
            frame,
            "OUTSIDE / DOOR",
            (LINE_X + 10, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2
        )

        cv2.putText(
            frame,
            "INSIDE ROOM",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2
        )

        for person in persons:
            person_id = person["id"]
            x1, y1, x2, y2 = person["box"]
            center_x, center_y = person["center"]

            current_side = get_side(center_x)

            print(
                f"[TRACK] ID={person_id} center_x={center_x} side={current_side}"
            )

            # draw box
            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

            # draw center point
            cv2.circle(
                frame,
                (center_x, center_y),
                5,
                (0, 0, 255),
                -1
            )

            cv2.putText(
                frame,
                f"ID:{person_id} {current_side}",
                (x1, max(y1 - 10, 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2
            )

            if person_id not in last_side:
                last_side[person_id] = current_side
                continue

            previous_side = last_side[person_id]

            event_type = None

            if previous_side == "OUTSIDE" and current_side == "INSIDE":
                event_type = "PERSON_ENTERED"

            elif previous_side == "INSIDE" and current_side == "OUTSIDE":
                event_type = "PERSON_EXITED"

            if event_type:
                now = datetime.now()

                if (
                    person_id not in last_event_time
                    or (now - last_event_time[person_id]).seconds > event_cooldown
                ):
                    event_time = now.strftime("%Y-%m-%d %H:%M:%S")

                    filename = now.strftime(
                        f"{captures_dir}/%Y%m%d_%H%M%S_{event_type}_ID{person_id}.jpg"
                    )

                    cv2.imwrite(filename, frame)

                    print(
                        f"[EVENT] {event_type} | ID={person_id} | {event_time}"
                    )

                    email_sent = 0

                    try:
                        if event_type == "PERSON_ENTERED":
                            notifier.send_alert(
                                image_path=filename,
                                event_time=event_time,
                                event_type=event_type
                            )
                            email_sent = 1

                    except Exception as e:
                        print(f"[EMAIL ERROR] {e}")

                    database.log_event(
                        event_time=event_time,
                        event_type=event_type,
                        image_path=filename,
                        email_sent=email_sent
                    )

                    last_event_time[person_id] = now

            last_side[person_id] = current_side

        cv2.imshow("Server Room Tripwire", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        # reduce CPU load
        time.sleep(0.1)

    camera.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
