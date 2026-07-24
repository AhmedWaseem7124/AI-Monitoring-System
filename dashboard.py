import sqlite3
from datetime import datetime
from flask import Flask, render_template

from app.config import load_config


app = Flask(
    __name__,
    template_folder="dashboard/templates",
    static_folder="dashboard/static"
)


def get_db_connection():
    config = load_config()
    db_path = config["storage"]["database_path"]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    return conn


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

    conn.close()

    return {
        "date": today,
        "entries_today": entries_today,
        "exits_today": exits_today,
        "emails_sent": emails_sent,
        "recent_events": recent_events,
        "last_event": last_event
    }


@app.route("/")
def index():
    data = get_dashboard_data()
    return render_template("index.html", data=data)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
