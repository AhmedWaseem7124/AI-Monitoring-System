# Server Room AI — Complete Local Network Deployment Procedure

## 1. Purpose

This document describes the complete procedure for deploying the Server Room AI Monitoring System on the company's local network and making it accessible through a company domain.

Target URL:

`serverroom.crescent.com.pk`

Target server IP:

`10.1.1.113`

The intended architecture is:

```text
Company LAN
    |
    v
serverroom.crescent.com.pk
    |
    v
Internal DNS
    |
    v
10.1.1.113
    |
    v
Nginx : 80 / 443
    |
    v
Gunicorn
    |
    v
Flask / Server Room AI
    |
    +--> CCTV Camera / RTSP
    +--> Face Recognition
    +--> SQLite Database
    +--> Email Alerts
    +--> Dashboard
    +--> Analytics
    +--> Reports
```

---

# 2. Current Server Network Configuration

The Server Room AI server was checked with the following commands:

```bash
hostname
hostname -I
ip addr
ip route
```

Current configuration:

```text
Hostname:          osamamansoor-HP-Z400-Workstation
LAN IP:            10.1.1.113
Network Interface: enp1s0
Gateway:           10.1.0.1
Network:           10.1.0.0/16
MAC Address:       78:e7:d1:c3:f0:65
IP Assignment:     DHCP
```

The IP address currently appears as DHCP-assigned.

Before relying on `10.1.1.113` for a DNS record, the IP should ideally be made persistent.

---

# 3. Step 1 — Make the Server IP Persistent

There are two recommended approaches.

## Option A — DHCP Reservation (Recommended)

If the company network administrator controls the DHCP server, create a DHCP reservation using:

```text
MAC Address: 78:e7:d1:c3:f0:65
Reserved IP: 10.1.1.113
```

This allows Ubuntu to continue using DHCP while ensuring that this specific server always receives `10.1.1.113`.

This is the preferred option for a company-managed network.

### Ask the IT/Network Administrator

Send the following request:

> Please create a DHCP reservation for the Server Room AI server.
>
> MAC Address: 78:e7:d1:c3:f0:65
> Requested IP: 10.1.1.113

The exact procedure depends on the company's DHCP infrastructure, such as:

- Windows Server DHCP
- MikroTik
- FortiGate
- Cisco
- UniFi
- Other network appliance

Do not configure a static IP on Ubuntu until it is confirmed that `10.1.1.113` is reserved or safely outside the DHCP allocation pool.

---

## Option B — Configure a Static IP on Ubuntu

Only use this option if the network administrator confirms the IP configuration.

The current network is:

```text
IP:       10.1.1.113
Prefix:   /16
Gateway:  10.1.0.1
Interface: enp1s0
```

DNS servers must be obtained from the company's network administrator or existing DHCP configuration.

Before making changes, inspect the current configuration:

```bash
ip addr
ip route
resolvectl status
```

On Ubuntu, the exact configuration method may depend on whether NetworkManager or Netplan is managing the interface.

After configuration, verify:

```bash
ip addr
ip route
ping -c 4 10.1.0.1
```

Then verify DNS resolution:

```bash
resolvectl status
```

If the server loses network connectivity after changing the configuration, revert the network change or consult the network administrator.

---

# 4. Step 2 — Verify the Server Room AI Application

Before configuring Nginx or DNS, make sure the application itself works correctly.

Go to the project:

```bash
cd ~/serverroom-ai-prod
```

Activate the virtual environment:

```bash
source venv/bin/activate
```

Check Python:

```bash
python --version
```

Compile the application:

```bash
python -m py_compile server.py
```

If there are no errors, start the application:

```bash
python server.py
```

From the server itself, test:

```text
http://127.0.0.1:5000
```

From another computer on the same LAN, test:

```text
http://10.1.1.113:5000
```

If the application is not reachable from another PC, verify that:

- Flask is listening on the LAN interface.
- Ubuntu firewall permits the required traffic.
- The two machines are on the same reachable network.
- The server IP is correct.

For production, do not rely on Flask's development server. The next steps configure Gunicorn and Nginx.

---

# 5. Step 3 — Install Production Dependencies

Update package information:

```bash
sudo apt update
```

Install Nginx:

```bash
sudo apt install nginx
```

Install Gunicorn inside the Python virtual environment:

```bash
cd ~/serverroom-ai-prod
source venv/bin/activate
pip install gunicorn
```

Verify:

```bash
gunicorn --version
nginx -v
```

---

# 6. Step 4 — Confirm the Flask Application Object

Gunicorn needs to know the Flask application object.

Check the bottom of `server.py`.

If the application is defined like:

```python
app = Flask(__name__)
```

then Gunicorn will normally use:

```bash
gunicorn server:app
```

If the file or Flask object has a different name, adjust the Gunicorn command accordingly.

Do not remove the existing:

```python
if __name__ == "__main__":
    ...
```

block unless you have confirmed that it is no longer needed for development.

---

# 7. Step 5 — Test Gunicorn Manually

From the project directory:

```bash
cd ~/serverroom-ai-prod
source venv/bin/activate
```

Start Gunicorn temporarily:

```bash
gunicorn --workers 1 --bind 127.0.0.1:8000 server:app
```

The application should now be available locally at:

```text
http://127.0.0.1:8000
```

Test from the server:

```bash
curl http://127.0.0.1:8000
```

If the application works, stop Gunicorn with:

```text
Ctrl + C
```

### Why use one worker initially?

The Server Room AI currently includes a long-running AI worker and CCTV processing. Using multiple Gunicorn workers can accidentally create multiple application processes and potentially multiple AI workers.

Start with:

```text
1 Gunicorn worker
```

until the AI architecture is separated into an independent background service.

---

# 8. Step 6 — Create a systemd Service

The goal is for Server Room AI to start automatically when Ubuntu boots.

Create the service:

```bash
sudo nano /etc/systemd/system/serverroom-ai.service
```

Use a configuration similar to:

```ini
[Unit]
Description=Server Room AI Monitoring System
After=network-online.target
Wants=network-online.target

[Service]
User=osamamansoor
Group=osamamansoor
WorkingDirectory=/home/osamamansoor/serverroom-ai-prod
Environment="PATH=/home/osamamansoor/serverroom-ai-prod/venv/bin"
ExecStart=/home/osamamansoor/serverroom-ai-prod/venv/bin/gunicorn --workers 1 --bind 127.0.0.1:8000 server:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Save the file.

Reload systemd:

```bash
sudo systemctl daemon-reload
```

Enable automatic startup:

```bash
sudo systemctl enable serverroom-ai
```

Start the service:

```bash
sudo systemctl start serverroom-ai
```

Check status:

```bash
sudo systemctl status serverroom-ai
```

View logs:

```bash
sudo journalctl -u serverroom-ai -f
```

If there is an error:

```bash
sudo journalctl -u serverroom-ai --no-pager -n 100
```

Restart:

```bash
sudo systemctl restart serverroom-ai
```

Stop:

```bash
sudo systemctl stop serverroom-ai
```

---

# 9. Important Architecture Consideration

The current application may start the AI worker from the Flask application process.

This means the architecture may currently be:

```text
systemd
    |
    v
Gunicorn
    |
    v
Flask
    |
    +--> AI Worker
    +--> Dashboard
```

This is acceptable for the initial single-server deployment if only one Gunicorn worker is used.

Do NOT increase Gunicorn workers without checking the AI worker architecture.

The long-term production architecture should be:

```text
systemd
    |
    +----------------------+
    |                      |
    v                      v
AI Worker Service      Gunicorn
    |                      |
    v                      v
CCTV / AI             Flask Dashboard
    |                      |
    +----------+-----------+
               |
               v
          SQLite Database
```

This allows the AI monitoring process to continue independently of the web dashboard.

---

# 10. Step 7 — Configure Nginx

Create an Nginx site:

```bash
sudo nano /etc/nginx/sites-available/serverroom-ai
```

Use:

```nginx
server {
    listen 80;
    server_name serverroom.crescent.com.pk;

    location / {
        proxy_pass http://127.0.0.1:8000;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 300;
        proxy_connect_timeout 300;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/serverroom-ai /etc/nginx/sites-enabled/serverroom-ai
```

Test configuration:

```bash
sudo nginx -t
```

If successful:

```bash
sudo systemctl reload nginx
```

Check Nginx:

```bash
sudo systemctl status nginx
```

At this point, Nginx expects:

```text
serverroom.crescent.com.pk
```

to resolve to:

```text
10.1.1.113
```

---

# 11. Step 8 — Configure Internal DNS

The company DNS administrator needs to create an A record.

Requested record:

```text
Type: A
Host: serverroom
Domain: crescent.com.pk
IP: 10.1.1.113
```

Result:

```text
serverroom.crescent.com.pk
        |
        v
10.1.1.113
```

Ask the IT/network administrator:

> Please create an internal DNS A record for `serverroom.crescent.com.pk` pointing to `10.1.1.113`.

If the company DNS system uses another naming convention, use the hostname approved by IT.

Do not create a public DNS record unless the application is intentionally meant to be accessible from the public Internet.

---

# 12. Step 9 — Test DNS

From a company computer connected to the company network:

```bash
nslookup serverroom.crescent.com.pk
```

or:

```bash
ping serverroom.crescent.com.pk
```

The hostname should resolve to:

```text
10.1.1.113
```

You can also use:

```bash
getent hosts serverroom.crescent.com.pk
```

If DNS does not resolve:

- Check the DNS A record.
- Check that the client uses the company's internal DNS server.
- Confirm the DNS record has propagated internally.
- Verify there is no split-DNS configuration issue.

---

# 13. Step 10 — Test the Domain

Open from a company PC:

```text
http://serverroom.crescent.com.pk
```

The request should flow:

```text
Browser
    |
    v
serverroom.crescent.com.pk
    |
    v
10.1.1.113
    |
    v
Nginx
    |
    v
127.0.0.1:8000
    |
    v
Gunicorn
    |
    v
Flask
```

Verify:

- Login works.
- Dashboard loads.
- CCTV feed works.
- Face recognition continues.
- Employee pages work.
- Analytics work.
- Reports work.
- Email alerts work.
- Event logging works.

---

# 14. Step 11 — Configure Firewall

Check UFW:

```bash
sudo ufw status
```

If UFW is active, allow HTTP:

```bash
sudo ufw allow 80/tcp
```

If HTTPS is later configured:

```bash
sudo ufw allow 443/tcp
```

Do not expose port `8000` publicly because Gunicorn is bound to:

```text
127.0.0.1:8000
```

Do not expose port `5000` in production unless there is a specific reason.

The intended external access path is:

```text
Client
  |
  v
Port 80/443
  |
  v
Nginx
  |
  v
Gunicorn on localhost
```

---

# 15. Step 12 — HTTPS

For an internal company application, HTTPS is recommended.

The preferred approach is to use the company's internal Certificate Authority (CA).

Request an internal certificate for:

```text
serverroom.crescent.com.pk
```

The certificate should be trusted by company-managed computers.

The final architecture becomes:

```text
https://serverroom.crescent.com.pk
```

Nginx handles HTTPS and forwards requests to:

```text
http://127.0.0.1:8000
```

The exact certificate installation procedure depends on the company's internal PKI/CA infrastructure.

Do not use a public certificate authority unless the hostname is publicly resolvable and the company policy permits it.

---

# 16. Step 13 — Verify Automatic Startup

Reboot the server:

```bash
sudo reboot
```

After the server comes back:

```bash
sudo systemctl status serverroom-ai
```

Check:

```bash
sudo systemctl status nginx
```

Then open from another company PC:

```text
http://serverroom.crescent.com.pk
```

The system should be available without manually running:

```bash
python server.py
```

The browser/dashboard can be closed at any time.

The AI monitoring service should continue running in the background.

---

# 17. Step 14 — Verify Background Operation

Close the browser.

The expected state is:

```text
Browser
    OFF

Dashboard
    OFF

AI Worker
    ON

CCTV Monitoring
    ON

Face Recognition
    ON

Database Logging
    ON

Email Alerts
    ON
```

The dashboard is only an interface for viewing the monitoring system.

The AI monitoring service should not depend on a browser being open.

---

# 18. Step 15 — Production Testing Checklist

## Network

- [ ] Server has persistent IP
- [ ] DNS record resolves correctly
- [ ] Server accessible from company LAN
- [ ] Gateway reachable
- [ ] Firewall configured

## Application

- [ ] Systemd service starts
- [ ] Application survives reboot
- [ ] Gunicorn works
- [ ] Nginx works
- [ ] Domain works

## AI

- [ ] CCTV connects
- [ ] Person detection works
- [ ] Face recognition works
- [ ] Unknown detection works
- [ ] Entry logging works
- [ ] Exit logging works

## Dashboard

- [ ] Login works
- [ ] Live feed works
- [ ] Employees work
- [ ] Employee profiles work
- [ ] Analytics work
- [ ] Reports work

## Notifications

- [ ] Unknown visitor email works
- [ ] Report email works
- [ ] Snapshots are attached correctly

## Reliability

- [ ] Browser can be closed
- [ ] AI continues running
- [ ] Server reboot tested
- [ ] Service automatically restarts
- [ ] Camera reconnect tested

---

# 19. Useful Commands

## Check IP

```bash
hostname -I
```

## Check interface

```bash
ip addr
```

## Check routes

```bash
ip route
```

## Check DNS

```bash
nslookup serverroom.crescent.com.pk
```

## Compile application

```bash
cd ~/serverroom-ai-prod
source venv/bin/activate
python -m py_compile server.py
```

## Check application service

```bash
sudo systemctl status serverroom-ai
```

## Restart application

```bash
sudo systemctl restart serverroom-ai
```

## Application logs

```bash
sudo journalctl -u serverroom-ai -f
```

## Check Nginx

```bash
sudo systemctl status nginx
```

## Test Nginx configuration

```bash
sudo nginx -t
```

## Reload Nginx

```bash
sudo systemctl reload nginx
```

## Check firewall

```bash
sudo ufw status
```

---

# 20. Troubleshooting

## Domain Does Not Open

Check:

```bash
nslookup serverroom.crescent.com.pk
```

If it does not resolve, contact IT/DNS administrator.

---

## Domain Resolves But Page Does Not Open

Check:

```bash
sudo systemctl status nginx
```

Then:

```bash
sudo nginx -t
```

Then:

```bash
sudo systemctl status serverroom-ai
```

---

## Nginx Shows 502 Bad Gateway

Check Gunicorn:

```bash
sudo systemctl status serverroom-ai
```

Check logs:

```bash
sudo journalctl -u serverroom-ai -n 100
```

Check locally:

```bash
curl http://127.0.0.1:8000
```

---

## Application Does Not Start After Reboot

Check:

```bash
sudo systemctl status serverroom-ai
```

Check:

```bash
sudo journalctl -u serverroom-ai -n 100
```

Make sure the virtual environment path in the systemd service is correct.

---

## AI Worker Does Not Run

Check application logs:

```bash
sudo journalctl -u serverroom-ai -f
```

Verify:

- Camera IP/RTSP URL
- Camera credentials
- Network connectivity
- Model files
- Face database
- Required environment variables

---

## Camera Does Not Connect

Test network reachability:

```bash
ping <camera-ip>
```

Check the RTSP URL and credentials.

Verify that the server can reach the camera VLAN/network.

---

# 21. Recommended Final Architecture

For the initial deployment:

```text
Company PC
    |
    v
serverroom.crescent.com.pk
    |
    v
Internal DNS
    |
    v
10.1.1.113
    |
    v
Nginx
    |
    v
Gunicorn (1 worker)
    |
    v
Flask Application
    |
    +--> AI Worker
    +--> CCTV
    +--> Face Recognition
    +--> SQLite
    +--> Email
```

For a future production architecture:

```text
Company PC
    |
    v
serverroom.crescent.com.pk
    |
    v
Internal DNS
    |
    v
Nginx
    |
    +---------------------+
    |                     |
    v                     v
Flask / Gunicorn      AI Worker Service
    |                     |
    |                     v
    |                 CCTV / RTSP
    |                     |
    +----------+----------+
               |
               v
         Database Layer
               |
       +-------+-------+
       |               |
       v               v
    Analytics       Reports
                       |
                       v
                  Email Alerts
```

This architecture is recommended once the project is fully stabilized.

---

# 22. Deployment Order Summary

Follow this exact order:

```text
1. Reserve 10.1.1.113
        |
        v
2. Verify Server Room AI locally
        |
        v
3. Install Gunicorn
        |
        v
4. Test Gunicorn manually
        |
        v
5. Create systemd service
        |
        v
6. Confirm application survives restart
        |
        v
7. Install/configure Nginx
        |
        v
8. Test Nginx locally
        |
        v
9. Create internal DNS record
        |
        v
10. Test DNS resolution
        |
        v
11. Test company domain
        |
        v
12. Configure firewall
        |
        v
13. Configure internal HTTPS
        |
        v
14. Test from multiple company PCs
        |
        v
15. Reboot server
        |
        v
16. Confirm automatic startup
        |
        v
17. Final production testing
```

---

# 23. Final Target

The completed deployment should allow an authorized employee on the company network to open:

```text
https://serverroom.crescent.com.pk
```

and access the Server Room AI dashboard.

The system should continuously monitor the server room even when:

- No browser is open.
- No user is viewing the dashboard.
- The dashboard is closed.
- The server is rebooted.

The AI monitoring service should automatically start after boot and continue processing CCTV footage, recognizing employees, logging events, generating alerts, and storing data.

---

# 24. Important Security Notes

- Do not commit passwords to Git.
- Store SMTP credentials in `.env`.
- Store camera credentials in `.env`.
- Store Flask secret keys in `.env`.
- Restrict access to the application to the company LAN or approved VLAN.
- Use HTTPS for production.
- Use strong administrator credentials.
- Do not expose SQLite or internal application ports directly to the network.
- Do not expose Gunicorn port `8000` externally.
- Keep port `5000` closed in production.
- Restrict SSH access to authorized administrators.
- Back up the SQLite database and important face datasets.
- Ensure company security policies permit storing employee face data.
- Protect `known_faces/`, `unknown_faces/`, and `captures/` because they may contain sensitive biometric or security information.

---

# 25. Current Deployment Information

```text
Application:
Server Room AI Monitoring System

Company Domain:
crescent.com.pk

Planned Application Domain:
serverroom.crescent.com.pk

Server Hostname:
osamamansoor-HP-Z400-Workstation

Server IP:
10.1.1.113

Network Interface:
enp1s0

MAC:
78:e7:d1:c3:f0:65

Gateway:
10.1.0.1

Network:
10.1.0.0/16

Project Directory:
/home/osamamansoor/serverroom-ai-prod

Virtual Environment:
/home/osamamansoor/serverroom-ai-prod/venv

Internal Application Port:
127.0.0.1:8000

Public LAN Access:
Nginx on port 80/443

Application Server:
Gunicorn

Reverse Proxy:
Nginx

Process Manager:
systemd
```

---

# 26. Final Note

The exact DHCP reservation and DNS configuration depend on the company's network infrastructure and administrative permissions.

The Server Room AI server currently uses DHCP, so the first action should be to make `10.1.1.113` persistent through a DHCP reservation or an IT-approved static IP configuration.

Once the IP is persistent and the internal DNS record exists, the application can be deployed behind Nginx and Gunicorn and made available at:

```text
serverroom.crescent.com.pk
```

The recommended deployment should be performed first on the internal LAN, tested thoroughly, and then secured with the company's internal HTTPS certificate before being treated as a production system.
