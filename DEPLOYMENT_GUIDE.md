# ADIPHAS: Deployment & Hosting Guide

This guide outlines the various pathways to host and share your project for your defense and potentially for real-world pilot use.

## 1. Local Network Sharing (Easiest for Defense)
If you are presenting in a room with a local WiFi network, you can allow other computers to access your system without uploading it to the web.
1. **Find your IP Address**: Run `ipconfig` in CMD. Look for `IPv4 Address` (e.g., `192.168.1.15`).
2. **Run Local Script**: Use the existing `./scripts/run_local_no_docker.ps1`.
3. **Access**: Others can visit `http://192.168.1.15:8501` to use the UI.

---

## 2. Containerized Deployment (Recommended)
You have a high-quality Docker setup already. This is the "Industry Standard" way to host.
1. **Build & Run**:
   ```bash
   docker-compose up --build -d
   ```
2. **Advantages**: 
   - Includes a **PostgreSQL** database out of the box.
   - Ensures the system works exactly the same on your laptop as it does on a cloud server.

---

## 3. Cloud Hosting Options

### Option A: Railway.app or Render.com (Simple MVP)
These are Platforms-as-a-Service (PaaS). They are very easy to use.
- **How**: Connect your GitHub repository. They will detect the `Dockerfile` and deploy it automatically.
- **Pros**: Automatic SSL (HTTPS), zero server management.
- **Cons**: Free tiers may "sleep" if inactive for a while.

### Option B: DigitalOcean or AWS Lightsail (Professional VPS)
A Virtual Private Server (VPS) gives you a dedicated Linux machine.
1. **Setup**: Rent a $5/month "Droplet" (DigitalOcean).
2. **Install**: Docker and Docker Compose.
3. **Deploy**: Clone your repo and run `docker-compose up`.
4. **Pros**: Permanent IP, always-on, high performance.

### Option C: Streamlit Community Cloud (Free UI Hosting)
You can host the UI for free specifically on Streamlit's own cloud.
- **Requirement**: Your backend API (FastAPI) must be hosted elsewhere first (like Option A or B).
- **Setup**: Link your GitHub repo to [share.streamlit.io](https://share.streamlit.io).

---

## 4. Key Security Checklist
Before going "Live" on the web, ensure:
1. **Environment Variables**: Never hardcode your `GEMINI_API_KEY` in the code. Always use the `.env` system.
2. **SQLite vs Postgres**: If using SQLite on a cloud server, ensure you define a **Persistent Volume** so your data (and alerts) aren't deleted when the server restarts.
3. **Port Access**: Only keep ports `8000` (API) and `8501` (UI) open.

---

## 5. Defense Pro-Tip
For your project evaluation, you can use a tool called **ngrok** to get a temporary public URL for your local machine:
```bash
ngrok http 8501
```
The examiner will be able to visit a link like `https://adiphas-demo.ngrok-free.app` and use your system immediately!
