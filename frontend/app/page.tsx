"use client";

import React, { useState, useEffect } from "react";
import {
  Calendar,
  Mail,
  CheckSquare,
  Sparkles,
  Send,
  FileText,
  Clock,
  AlertCircle,
  CheckCircle2,
  Trash2,
  Zap,
  Terminal,
  RefreshCw,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return API_KEY ? { ...extra, "X-API-Key": API_KEY } : extra;
}

export default function ExecutiveDashboard() {
  const [mode, setMode] = useState<"command" | "notes">("command");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [cronLoading, setCronLoading] = useState(false);
  const [agentReply, setAgentReply] = useState<string | null>(null);

  const [events, setEvents] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [emails, setEmails] = useState<any[]>([]);
  const [logs, setLogs] = useState<any[]>([]);

  const fetchDashboard = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/dashboard`);
      const data = await res.json();
      setEvents(data.events || []);
      setTasks(data.tasks || []);
      setEmails(data.emails || []);
      setLogs(data.logs || []);
    } catch (err) {
      console.error("Failed to fetch dashboard:", err);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  const handleExecute = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    setLoading(true);
    setAgentReply(null);
    try {
      const res = await fetch(`${API_BASE}/api/agent/execute`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ prompt: input, mode }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Execution error");
      setAgentReply(data.reply);
      setInput("");
      await fetchDashboard();
    } catch (err: any) {
      setAgentReply(`⚠️ Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleTriggerBriefing = async () => {
    setCronLoading(true);
    setAgentReply(null);
    try {
      const res = await fetch(`${API_BASE}/api/cron/morning-briefing`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Briefing error");
      setAgentReply(data.briefing);
      await fetchDashboard();
    } catch (err: any) {
      setAgentReply(`⚠️ Error triggering briefing: ${err.message}`);
    } finally {
      setCronLoading(false);
    }
  };

  const toggleTask = async (id: number) => {
    try {
      await fetch(`${API_BASE}/api/tasks/${id}/toggle`, { method: "POST", headers: authHeaders() });
    } finally {
      fetchDashboard();
    }
  };

  const deleteTask = async (id: number) => {
    try {
      await fetch(`${API_BASE}/api/tasks/${id}`, { method: "DELETE", headers: authHeaders() });
    } finally {
      fetchDashboard();
    }
  };

  const fillSampleCommand = () => {
    setMode("command");
    setInput(
      "Book a 30-minute Product Roadmap Sync with alex@company.com today at 14:00 (check for conflicts first), email him the agenda, and add an Urgent task to review the Q4 budget today."
    );
  };

  const fillSampleNotes = () => {
    setMode("notes");
    setInput(
      `Meeting Notes - Customer Discovery Call with David (david@enterprise.io):
- David wants a follow-up technical demo tomorrow from 11:00 to 12:00. Please book it on the calendar.
- Send David a follow-up email thanking him for his time and confirming tomorrow's technical demo.
- Action item: Prepare custom enterprise security documentation (Urgent priority, due today).
- Action item: Share API rate-limit benchmarks with engineering team (Normal priority).`
    );
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 font-sans">
      {/* Top Navbar */}
      <header className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-6 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-600/20 border border-indigo-500/40 text-indigo-400">
              <Sparkles className="w-6 h-6" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white">
              AI Executive Assistant
            </h1>
            <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-medium">
              Gemini Flash • Active
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Autonomous Conflict-Aware Scheduling, Multi-Step Notes-to-Action, Follow-Up Emails & Proactive Briefings
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleTriggerBriefing}
            disabled={cronLoading}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30 text-sm font-medium transition cursor-pointer disabled:opacity-50"
          >
            <Zap className="w-4 h-4" />
            {cronLoading
              ? "Running Morning Briefing..."
              : "⚡ Trigger Proactive Morning Briefing (Cron)"}
          </button>
          <button
            onClick={fetchDashboard}
            className="p-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 transition"
            title="Refresh Dashboard"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto mt-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* LEFT COLUMN: Command Center & Live Execution Trace (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          {/* Command & Notes Box */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <div className="flex gap-2 bg-slate-950 p-1 rounded-xl border border-slate-800">
                <button
                  type="button"
                  onClick={() => setMode("command")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition flex items-center gap-1.5 ${
                    mode === "command"
                      ? "bg-indigo-600 text-white"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  Smart Command
                </button>
                <button
                  type="button"
                  onClick={() => setMode("notes")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition flex items-center gap-1.5 ${
                    mode === "notes"
                      ? "bg-indigo-600 text-white"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  <FileText className="w-3.5 h-3.5" />
                  Notes-to-Action Extractor
                </button>
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={fillSampleCommand}
                  className="text-xs text-indigo-400 hover:text-indigo-300 underline"
                >
                  Demo Conflict Command
                </button>
                <span className="text-slate-700">|</span>
                <button
                  type="button"
                  onClick={fillSampleNotes}
                  className="text-xs text-indigo-400 hover:text-indigo-300 underline"
                >
                  Demo Meeting Notes
                </button>
              </div>
            </div>

            <form onSubmit={handleExecute}>
              <textarea
                rows={mode === "notes" ? 6 : 4}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  mode === "command"
                    ? "e.g., Book a 30-min call with Sarah today at 14:00, email her the agenda, and remind me to review the deck..."
                    : "Paste messy meeting notes or an email thread here. The AI will automatically book all meetings, send follow-up emails, and extract to-do items..."
                }
                className="w-full rounded-xl bg-slate-950 border border-slate-800 p-3.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
              <button
                type="submit"
                disabled={loading}
                className="mt-3 w-full py-2.5 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-sm flex items-center justify-center gap-2 transition disabled:opacity-50 cursor-pointer"
              >
                <Send className="w-4 h-4" />
                {loading
                  ? "Agent Executing Multi-Step Workflow..."
                  : mode === "command"
                  ? "Execute Assistant Command"
                  : "Extract & Execute All Actions"}
              </button>
            </form>

            {/* Agent Response Output */}
            {agentReply && (
              <div className="mt-4 p-4 rounded-xl bg-indigo-950/30 border border-indigo-500/30 text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">
                <div className="text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-1.5 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5" /> Executive Assistant Output
                </div>
                {agentReply}
              </div>
            )}
          </div>

          {/* Live Step-by-Step Action Log */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <Terminal className="w-4 h-4 text-emerald-400" />
                Live Agent Tool Execution Log
              </h2>
              <span className="text-xs text-slate-500">Real-Time Trace</span>
            </div>

            <div className="space-y-2.5 max-h-80 overflow-y-auto pr-1">
              {logs.length === 0 ? (
                <p className="text-xs text-slate-500 py-4 text-center">
                  No tool executions yet. Run a command above!
                </p>
              ) : (
                logs.map((log, index) => (
                  <div
                    key={log.id || index}
                    className="p-2.5 rounded-xl bg-slate-950 border border-slate-800/80 text-xs flex items-start gap-2.5"
                  >
                    <span className="px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-mono shrink-0">
                      {log.step_type}
                    </span>
                    <span className="text-slate-300 flex-1">{log.message}</span>
                    <span className="text-slate-600 font-mono shrink-0">
                      {log.timestamp}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Live Overview (Calendar, Tasks, Sent Emails) (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          {/* 1. Google Calendar Schedule */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                <Calendar className="w-4 h-4 text-indigo-400" />
                Conflict-Aware Google Calendar Schedule
              </h2>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                {events.length} Synced Events
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {events.map((evt) => (
                <div
                  key={evt.id}
                  className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="font-semibold text-sm text-white">
                        {evt.title}
                      </h3>
                      <span className="text-[11px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        Confirmed
                      </span>
                    </div>
                    <p className="text-xs text-indigo-400 mt-1 flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" />
                      {evt.start_time.replace("T", " ")} →{" "}
                      {evt.end_time.slice(-5)}
                    </p>
                    {evt.attendees && (
                      <p className="text-xs text-slate-400 mt-1">
                        👤 Attendee: {evt.attendees}
                      </p>
                    )}
                  </div>
                  {evt.description && (
                    <p className="text-xs text-slate-500 mt-2 pt-2 border-t border-slate-900">
                      {evt.description}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* 2. Smart Task & Reminder Board */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                <CheckSquare className="w-4 h-4 text-amber-400" />
                Smart Task & Reminder Board
              </h2>
              <span className="text-xs text-slate-400">
                {tasks.filter((t) => t.status === "pending").length} Pending
              </span>
            </div>

            <div className="space-y-2.5">
              {tasks.map((task) => (
                <div
                  key={task.id}
                  className={`p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between gap-3 ${
                    task.status === "completed" ? "opacity-50" : ""
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => toggleTask(task.id)}
                      className="text-slate-400 hover:text-emerald-400 transition cursor-pointer"
                    >
                      <CheckCircle2
                        className={`w-5 h-5 ${
                          task.status === "completed"
                            ? "text-emerald-500"
                            : "text-slate-600"
                        }`}
                      />
                    </button>
                    <div>
                      <p
                        className={`text-sm font-medium ${
                          task.status === "completed"
                            ? "line-through text-slate-500"
                            : "text-slate-200"
                        }`}
                      >
                        {task.title}
                      </p>
                      <span className="text-xs text-slate-500">
                        Due: {task.due_date || "Today"}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs px-2.5 py-0.5 rounded-full font-medium border ${
                        task.priority === "Urgent"
                          ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                          : task.priority === "Normal"
                          ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                          : "bg-slate-800 text-slate-400 border-slate-700"
                      }`}
                    >
                      {task.priority}
                    </span>
                    <button
                      onClick={() => deleteTask(task.id)}
                      className="p-1 text-slate-600 hover:text-rose-400 transition cursor-pointer"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 3. Automated Follow-Up Emails & Briefings Dispatched */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                <Mail className="w-4 h-4 text-sky-400" />
                Automated Follow-Up Emails & Briefings Dispatched
              </h2>
              <span className="text-xs text-slate-400">
                {emails.length} Sent
              </span>
            </div>

            <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
              {emails.length === 0 ? (
                <p className="text-xs text-slate-500 py-4 text-center">
                  No automated emails sent yet.
                </p>
              ) : (
                emails.map((em) => (
                  <div
                    key={em.id}
                    className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-sky-400">
                        To: {em.recipient}
                      </span>
                      <span className="text-[11px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                        {em.status} • {em.sent_at}
                      </span>
                    </div>
                    <h4 className="text-sm font-semibold text-white">
                      {em.subject}
                    </h4>
                    <p className="text-xs text-slate-400 whitespace-pre-wrap line-clamp-4">
                      {em.body}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}