"""HTTP endpoints.

Thin layer on purpose: request/response shaping and error translation only.
Business logic lives in `agent`, `briefing` and `tools`.

    POST   /api/agent/execute        run the assistant on a prompt
    POST   /api/cron/morning-briefing  external trigger for the daily briefing
    GET    /api/health               integration status
    GET    /api/dashboard            events + tasks + emails + activity log
    POST   /api/tasks/{id}/toggle    flip pending <-> completed
    DELETE /api/tasks/{id}           delete a task
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .agent import AgentNotConfigured, AgentOverloaded, run_agent
from .briefing import run_morning_briefing
from .database import connect
from .diagnostics import health_payload
from .security import require_api_key

router = APIRouter()


class AgentRequest(BaseModel):
    prompt: str
    mode: str = "command"  # "command" | "notes" (hint for the system prompt)


@router.get("/api/health")
def health():
    return health_payload()


@router.post("/api/agent/execute", dependencies=[Depends(require_api_key)])
def execute_agent(request: AgentRequest):
    try:
        return run_agent(request.prompt, request.mode)
    except AgentNotConfigured as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except AgentOverloaded as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001 - surface the message to the UI
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/api/cron/morning-briefing", dependencies=[Depends(require_api_key)])
def morning_briefing():
    return run_morning_briefing()


@router.get("/api/dashboard")
def dashboard():
    conn = connect(sqlite3.Row)
    try:
        events = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM calendar_events ORDER BY start_time ASC"
            ).fetchall()
        ]
        tasks = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM tasks "
                "ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, "
                "CASE priority WHEN 'Urgent' THEN 1 WHEN 'Normal' THEN 2 ELSE 3 END, "
                "id DESC"
            ).fetchall()
        ]
        emails = [
            dict(row)
            for row in conn.execute("SELECT * FROM emails ORDER BY id DESC LIMIT 15").fetchall()
        ]
        logs = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM action_logs ORDER BY id DESC LIMIT 25"
            ).fetchall()
        ]
    finally:
        conn.close()

    return {"events": events, "tasks": tasks, "emails": emails, "logs": logs}


@router.post("/api/tasks/{task_id}/toggle", dependencies=[Depends(require_api_key)])
def toggle_task(task_id: int):
    conn = connect()
    try:
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row:
            new_status = "completed" if row[0] == "pending" else "pending"
            conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))
            conn.commit()
    finally:
        conn.close()
    return {"status": "updated"}


@router.delete("/api/tasks/{task_id}", dependencies=[Depends(require_api_key)])
def delete_task(task_id: int):
    conn = connect()
    try:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    finally:
        conn.close()
    return {"status": "deleted"}
