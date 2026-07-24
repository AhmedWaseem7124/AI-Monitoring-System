import smtplib
import os
from email.message import EmailMessage


class EmailNotifier:

    def send_email_with_attachment_to(self, recipient, subject, body, attachment_bytes, filename):
        msg = EmailMessage()

        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = recipient

        msg.set_content(body)

        msg.add_attachment(
            attachment_bytes,
            maintype="application",
            subtype="pdf",
            filename=filename
        )

        smtp = smtplib.SMTP(self.server, self.port)
        smtp.send_message(msg)
        smtp.quit()

        print(f"[EMAIL] Report sent to {recipient}")

    def send_email_with_attachment(self, subject, body, attachment_bytes, filename):
        msg = EmailMessage()

        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = self.recipient

        msg.set_content(body)

        msg.add_attachment(
            attachment_bytes,
            maintype="application",
            subtype="pdf",
            filename=filename
        )

        smtp = smtplib.SMTP(self.server, self.port)
        smtp.send_message(msg)
        smtp.quit()

        print("[EMAIL] Report sent with attachment")
    def __init__(self, smtp_config):
        self.server = smtp_config["server"]
        self.port = smtp_config["port"]
        self.sender = smtp_config["sender"]
        self.recipient = smtp_config["recipient"]

    def send_alert(self, image_path, event_time, event_type="PERSON_DETECTED"):
        msg = EmailMessage()

        msg["Subject"] = f"[AI ALERT] {event_type}"
        msg["From"] = self.sender
        msg["To"] = self.recipient

        msg.set_content(
            f"""
Server Room AI Monitoring Alert

Event: {event_type}
Time: {event_time}

A person was detected in the server room.

Snapshot attached.
"""
        )

        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                msg.add_attachment(
                    f.read(),
                    maintype="image",
                    subtype="jpeg",
                    filename=os.path.basename(image_path)
                )

        smtp = smtplib.SMTP(self.server, self.port)
        smtp.send_message(msg)
        smtp.quit()

        print("[EMAIL] Alert sent")

    def send_text_email(self, subject, body):
        msg = EmailMessage()

        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = self.recipient

        msg.set_content(body)

        smtp = smtplib.SMTP(self.server, self.port)
        smtp.send_message(msg)
        smtp.quit()

        print("[EMAIL] Text email sent")

    def send_html_email(self, subject, html_body, plain_text_body=None):
        msg = EmailMessage()

        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = self.recipient

        if plain_text_body is None:
            plain_text_body = "Please view this email in an HTML-supported email client."

        msg.set_content(plain_text_body)
        msg.add_alternative(html_body, subtype="html")

        smtp = smtplib.SMTP(self.server, self.port)
        smtp.send_message(msg)
        smtp.quit()

        print("[EMAIL] HTML email sent")
