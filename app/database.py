import sqlite3


class EventDatabase:
    def __init__(self, db_path):
        self.db_path = db_path

    def log_event(self, event_time, event_type, image_path, email_sent=0, person_name="UNKNOWN"):
        conn = sqlite3.connect(self.db_path)

        conn.execute(
            """
            INSERT INTO events
            (event_time, event_type, image_path, email_sent, person_name)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_time, event_type, image_path, email_sent, person_name)
        )

        conn.commit()
        conn.close()

        print(f"[DB] Event logged | {person_name} | {event_type}")
