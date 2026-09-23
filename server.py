#!/usr/bin/env python3
"""Sana Bridge — local hackathon MVP, Python standard library only."""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from datetime import datetime, timezone
import uuid

from domain import FIELDS, TOPICS, MILESTONES, ValidationError, analyze, clean_card, rating, text_value, valid_url

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "sana.sqlite3"

def now(): return datetime.now(timezone.utc).isoformat()
def uid(prefix): return prefix + uuid.uuid4().hex[:12]
def encode(value): return json.dumps(value, ensure_ascii=False)

def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, owner TEXT NOT NULL, topic TEXT NOT NULL,
          fields TEXT NOT NULL, confirmed TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0,
          revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS teams(id TEXT PRIMARY KEY, profile TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
          team_id TEXT NOT NULL REFERENCES teams(id), idea TEXT NOT NULL, plan TEXT NOT NULL,
          timeline TEXT NOT NULL, link TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS milestones(id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id),
          stage TEXT NOT NULL, evidence TEXT NOT NULL, note TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'submitted',
          feedback TEXT NOT NULL DEFAULT '', points INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
          UNIQUE(proposal_id, stage));
        """)
        if db.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 0:
            seed = json.loads((ROOT / "data" / "seed.json").read_text(encoding="utf-8"))
            for t in seed["teams"]: db.execute("INSERT INTO teams VALUES(?,?)", (t["id"], encode(t)))
            for t in seed["cards"]:
                db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)", (t["id"], "business", t["topic"], encode(t["fields"]), encode(t["confirmed"]), 1, 1, now(), now()))
            for p in seed["proposals"]:
                db.execute("INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?,?)", (p["id"], p["task_id"], p["team_id"], p["idea"], p["plan"], p["timeline"], p["link"], "pending", now()))

def task_json(row):
    t = dict(row)
    t["fields"] = json.loads(t["fields"])
    t["confirmed"] = json.loads(t["confirmed"])
    t["published"] = bool(t["published"])
    t["rating"] = rating(t["fields"], t["confirmed"])
    return t

class ApiError(Exception):
    def __init__(self, message, status=400): self.message, self.status = message, status

class Handler(BaseHTTPRequestHandler):
    server_version = "SanaBridge/1.0"

    def log_message(self, fmt, *args):
        if os.environ.get("SANA_QUIET") != "1": super().log_message(fmt, *args)

    def send(self, status, body, content_type="application/json; charset=utf-8"):
        data = encode(body).encode("utf-8") if "application/json" in content_type else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        try: size = int(self.headers.get("Content-Length", "0"))
        except ValueError: raise ApiError("Сұрау өлшемі қате.")
        if not 0 < size <= 80000: raise ApiError("Сұрау өлшемі 1–80000 байт болуы керек.", 413)
        if "application/json" not in self.headers.get("Content-Type", ""): raise ApiError("JSON қажет.", 415)
        try: body = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError): raise ApiError("JSON синтаксисі қате.")
        if not isinstance(body, dict): raise ApiError("JSON объектісі қажет.")
        return body

    def role(self):
        role = self.headers.get("X-Demo-Role", "student")
        if role not in ("student", "business"): raise ApiError("Рөл дұрыс емес.", 403)
        return role

    def business(self):
        if self.role() != "business": raise ApiError("Бұл әрекетті бизнес өкілі орындайды.", 403)

    def team(self, db):
        if self.role() != "student": raise ApiError("Бұл әрекетті студенттік команда орындайды.", 403)
        team_id = self.headers.get("X-Team-ID", "")
        if not db.execute("SELECT id FROM teams WHERE id=?", (team_id,)).fetchone(): raise ApiError("Команданы таңдаңыз.", 403)
        return team_id

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path == "/api/state":
                with connect() as db:
                    tasks = [task_json(r) for r in db.execute("SELECT * FROM tasks") if r["published"] or self.role() == "business"]
                    tasks.sort(key=lambda t: (-t["rating"]["score"], t["created_at"], t["id"]))
                    teams = []
                    for r in db.execute("SELECT * FROM teams"):
                        team = json.loads(r["profile"])
                        team["points"] = db.execute("SELECT COALESCE(SUM(m.points),0) FROM milestones m JOIN proposals p ON m.proposal_id=p.id WHERE p.team_id=? AND m.status='approved'", (team["id"],)).fetchone()[0]
                        teams.append(team)
                    proposals = [dict(r) for r in db.execute("SELECT * FROM proposals ORDER BY created_at DESC") if self.role() == "business" or r["team_id"] == self.headers.get("X-Team-ID")]
                    ids = {p["id"] for p in proposals}
                    milestones = [dict(r) for r in db.execute("SELECT * FROM milestones") if r["proposal_id"] in ids]
                self.send(200, {"tasks": tasks, "teams": teams, "proposals": proposals, "milestones": milestones, "topics": TOPICS,
                                "milestone_definitions": {k: {"label": v[0], "points": v[1]} for k,v in MILESTONES.items()}})
            elif path == "/api/demo":
                self.send(200, json.loads((ROOT / "data" / "demo.json").read_text(encoding="utf-8")))
            elif path in ("/", "/index.html", "/app.js", "/styles.css"):
                file = ROOT / "static" / ("index.html" if path == "/" else path[1:])
                self.send(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or "text/plain") + "; charset=utf-8")
            else: self.send(404, {"error": "Бет табылмады."})
        except ApiError as e: self.send(e.status, {"error": e.message})
        except Exception:
            self.send(500, {"error": "Сервер қатесі. Қайта көріңіз."})

    def do_POST(self):
        try:
            # JSON/custom headers plus Origin validation prevent cross-site form writes.
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                raise ApiError("Бөгде сайттан сұрау қабылданбайды.", 403)
            body = self.body()
            path = urlsplit(self.path).path
            parts = path.strip("/").split("/")
            if path == "/api/analyze":
                self.business()
                self.send(200, analyze(body)); return
            if path == "/api/rating":
                fields, _, confirmed = clean_card(body, require_title=False)
                self.send(200, rating(fields, confirmed)); return
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if path == "/api/tasks":
                    self.business()
                    fields, topic, confirmed = clean_card(body)
                    if body.get("publish") is True and any(v and k not in confirmed for k,v in fields.items()):
                        raise ApiError("Жариялау алдында барлық толтырылған өрісті растаңыз.")
                    task_id = uid("task_")
                    db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)", (task_id, "business", topic, encode(fields), encode(confirmed), int(body.get("publish") is True), 1, now(), now()))
                    result = {"id": task_id}
                elif len(parts) == 3 and parts[:2] == ["api", "tasks"]:
                    self.business()
                    row = db.execute("SELECT * FROM tasks WHERE id=?", (parts[2],)).fetchone()
                    if not row: raise ApiError("Міндет табылмады.", 404)
                    if body.get("revision") != row["revision"]: raise ApiError("Карточка басқа терезеде өзгерді. Қайта ашыңыз.", 409)
                    fields, topic, confirmed = clean_card(body)
                    published = bool(row["published"]) or body.get("publish") is True
                    if published and any(v and k not in confirmed for k,v in fields.items()):
                        raise ApiError("Жарияланған карточканың барлық толтырылған өрісін растаңыз.")
                    db.execute("UPDATE tasks SET fields=?,topic=?,confirmed=?,published=?,revision=revision+1,updated_at=? WHERE id=?", (encode(fields), topic, encode(confirmed), int(published), now(), parts[2]))
                    result = {"id": parts[2]}
                elif path == "/api/proposals":
                    team_id = self.team(db)
                    task = db.execute("SELECT * FROM tasks WHERE id=? AND published=1", (body.get("task_id"),)).fetchone()
                    if not task: raise ApiError("Жарияланған міндет табылмады.", 404)
                    idea = text_value(body.get("idea"), "Шешім идеясы", 15)
                    plan = text_value(body.get("plan"), "Жоспар", 15)
                    timeline = text_value(body.get("timeline"), "Мерзім", 3, 180)
                    link = text_value(body.get("link"), "Прототип сілтемесі", 8, 1000)
                    if not valid_url(link): raise ApiError("Прототипке жарамды http/https сілтемесін енгізіңіз.")
                    proposal_id = uid("prop_")
                    db.execute("INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?,?)", (proposal_id, task["id"], team_id, idea, plan, timeline, link, "pending", now()))
                    result = {"id": proposal_id}
                elif len(parts) == 4 and parts[:2] == ["api", "proposals"] and parts[3] == "decision":
                    self.business()
                    status = body.get("status")
                    if status not in ("accepted", "rejected"): raise ApiError("Шешімді таңдаңыз.")
                    p = db.execute("SELECT * FROM proposals WHERE id=?", (parts[2],)).fetchone()
                    if not p: raise ApiError("Ұсыныс табылмады.", 404)
                    if status == "rejected" and db.execute("SELECT id FROM milestones WHERE proposal_id=?", (p["id"],)).fetchone():
                        raise ApiError("Кезең басталған ұсынысты қабылдамау мүмкін емес.", 409)
                    db.execute("UPDATE proposals SET status=? WHERE id=?", (status, p["id"]))
                    result = {"id": p["id"], "status": status}
                elif path == "/api/milestones":
                    team_id = self.team(db)
                    p = db.execute("SELECT * FROM proposals WHERE id=?", (body.get("proposal_id"),)).fetchone()
                    if not p or p["team_id"] != team_id or p["status"] != "accepted": raise ApiError("Тек таңдалған өз командаңыз кезең жібере алады.", 403)
                    stage = body.get("stage")
                    if stage not in MILESTONES: raise ApiError("Кезеңді таңдаңыз.")
                    evidence = text_value(body.get("evidence"), "Нәтиже сілтемесі", 8, 1000)
                    if not valid_url(evidence): raise ApiError("Нәтижеге жарамды http/https сілтемесі қажет.")
                    note = text_value(body.get("note"), "Орындалған жұмыс", 15)
                    old = db.execute("SELECT * FROM milestones WHERE proposal_id=? AND stage=?", (p["id"], stage)).fetchone()
                    if old and old["status"] != "revision": raise ApiError("Бұл кезең жіберілген немесе расталған.", 409)
                    milestone_id = old["id"] if old else uid("stage_")
                    if old:
                        db.execute("UPDATE milestones SET evidence=?,note=?,status='submitted',feedback='',created_at=? WHERE id=?", (evidence, note, now(), milestone_id))
                    else:
                        db.execute("INSERT INTO milestones VALUES(?,?,?,?,?,'submitted','',0,?)", (milestone_id, p["id"], stage, evidence, note, now()))
                    result = {"id": milestone_id}
                elif len(parts) == 4 and parts[:2] == ["api", "milestones"] and parts[3] == "review":
                    self.business()
                    m = db.execute("SELECT * FROM milestones WHERE id=?", (parts[2],)).fetchone()
                    if not m: raise ApiError("Кезең табылмады.", 404)
                    if m["status"] != "submitted": raise ApiError("Бұл кезең қаралған. Ұпай қайта берілмейді.", 409)
                    decision = body.get("decision")
                    if decision not in ("approved", "revision"): raise ApiError("Кезең бойынша шешім қажет.")
                    feedback = text_value(body.get("feedback", ""), "Кері байланыс", 5 if decision == "revision" else 0)
                    points = MILESTONES[m["stage"]][1] if decision == "approved" else 0
                    db.execute("UPDATE milestones SET status=?,feedback=?,points=? WHERE id=?", (decision, feedback, points, m["id"]))
                    result = {"id": m["id"], "points": points}
                else: raise ApiError("Әрекет табылмады.", 404)
            # Commit precedes success response, so subsequent reads see the write.
            self.send(200, result)
        except (ApiError, ValidationError) as e: self.send(e.status if isinstance(e, ApiError) else 400, {"error": e.message if isinstance(e, ApiError) else str(e)})
        except (sqlite3.IntegrityError, sqlite3.OperationalError): self.send(409, {"error": "Деректер қайшылығы. Бетті жаңартып қайталаңыз."})
        except Exception:
            import traceback
            traceback.print_exc()
            self.send(500, {"error": "Сервер қатесі. Енгізілген мәліметтерді тексеріп, қайта көріңіз."})

def main():
    global DB_PATH
    parser = argparse.ArgumentParser(description="Sana Bridge MVP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()
    DB_PATH = args.db.resolve()
    init_db()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Sana Bridge: http://{args.host}:{server.server_port}\nТоқтату: Ctrl+C", flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nСервер тоқтады.")
    finally: server.server_close()

if __name__ == "__main__": main()
