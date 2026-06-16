import customtkinter as ctk
import json
import os
import mysql.connector
import random
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tkinter import messagebox, filedialog
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
#  OPTIONAL IMPORTS
# ─────────────────────────────────────────────────────────────────────────────
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    sr = None
    SR_AVAILABLE = False

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    pd = None
    PANDAS_AVAILABLE = False

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
#  THEME
# ─────────────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

ACCENT       = ("#4F46E5", "#6366F1")
BG_MAIN      = ("#F1F5F9", "#0F0F13")
BG_CARD      = ("#FFFFFF", "#1A1A22")
CARD_INNER   = ("#F8FAFC", "#252530")
TEXT_PALE    = ("#475569", "#94A3B8")
TEXT_MAIN    = ("#1E293B", "#F1F5F9")
SUCCESS      = "#22C55E"
DANGER       = "#EF4444"
ACCENT_HOVER = ("#4338CA", "#4F46E5")
BORDER       = ("#CBD5E1", "#2D2D39")
WARNING      = "#F59E0B"


class AIAssistant:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://integrate.api.nvidia.com/v1"
        self.client = None
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        except ImportError:
            pass

    def ask(self, prompt, context_data):
        if not self.client:
            return "AI Error: pip install openai"
        try:
            ctx = json.dumps({
                "teachers": context_data.get("teachers", []),
                "subjects": context_data.get("subjects", []),
                "classes": context_data.get("classes", []),
                "expertise": context_data.get("teacher_expertise", {}),
            })
            resp = self.client.chat.completions.create(
                model="meta/llama-3.1-8b-instruct",
                messages=[
                    {"role": "system", "content": f"You are Scheduler Pro AI. Respond in user's language (Hindi/English/Hinglish). Data: {ctx}"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5, max_tokens=600,
            )
            return resp.choices[0].message.content
        except Exception as exc:
            return f"AI Error: {exc}"


class TimetableMLAnalyzer:
    def predict_burnout(self, teacher_stats):
        risks = {}
        for t, data in teacher_stats.items():
            score = (data.get("total", 0) / 40 * 0.4) + (data.get("max_consecutive", 0) / 4 * 0.6)
            risks[t] = min(round(score, 2), 1.0)
        return risks


class TimetableApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Timetable Scheduler Pro")
        self.geometry("1400x900")
        self.minsize(1200, 750)
        self.configure(fg_color=BG_MAIN)

        self.db_config = {
            "host": "localhost",
            "user": "root",
            "password": "Aniket8253051016",
            "database": "timetable_db",
        }

        self.ai = AIAssistant("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")
        self.ml_analyzer = TimetableMLAnalyzer()

        self.current_manage_filter = "teachers"
        self.current_user_role = None
        self.current_username = None
        self.login_mode_switch_ref = None
        self.generated_timetable = {}
        self.data = {}
        self._ai_win = None
        self._is_listening = False

        self.init_db()
        self.load_data()
        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.show_login()

    def init_db(self):
        tables = [
            "CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(100) UNIQUE NOT NULL, password VARCHAR(255) NOT NULL, role VARCHAR(20) DEFAULT 'viewer')",
            "CREATE TABLE IF NOT EXISTS teachers (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(150) UNIQUE NOT NULL, email VARCHAR(200) DEFAULT '', phone VARCHAR(20) DEFAULT '', is_deleted TINYINT(1) DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS subjects (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(150) UNIQUE NOT NULL, is_deleted TINYINT(1) DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS classes (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(150) UNIQUE NOT NULL, is_deleted TINYINT(1) DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS classrooms (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(150) UNIQUE NOT NULL, is_deleted TINYINT(1) DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS lab_rooms (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(150) UNIQUE NOT NULL, is_deleted TINYINT(1) DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS teacher_expertise (id INT AUTO_INCREMENT PRIMARY KEY, teacher VARCHAR(150) NOT NULL, subject VARCHAR(150) NOT NULL, UNIQUE KEY uq_te (teacher, subject))",
            "CREATE TABLE IF NOT EXISTS timetable_entries (id INT AUTO_INCREMENT PRIMARY KEY, class_name VARCHAR(150), day VARCHAR(20), period INT, subject VARCHAR(150), teacher VARCHAR(150), room VARCHAR(150), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS feedback (id INT AUTO_INCREMENT PRIMARY KEY, teacher VARCHAR(150), message TEXT, sentiment VARCHAR(50), issue_type VARCHAR(50), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS ai_history (id INT AUTO_INCREMENT PRIMARY KEY, role VARCHAR(20), content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        ]
        try:
            cfg = {k: v for k, v in self.db_config.items() if k != "database"}
            conn = mysql.connector.connect(**cfg)
            cur = conn.cursor()
            cur.execute("CREATE DATABASE IF NOT EXISTS timetable_db")
            conn.commit()
            conn.close()

            conn = mysql.connector.connect(**self.db_config)
            cur = conn.cursor()
            for tbl in tables:
                cur.execute(tbl)
            cur.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()[0] == 0:
                cur.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", ("admin", "admin123", "admin"))
            conn.commit()
            conn.close()
        except Exception as exc:
            messagebox.showerror("DB Error", str(exc))

    def get_connection(self):
        return mysql.connector.connect(**self.db_config)

    def load_data(self):
        try:
            conn = self.get_connection()
            cur = conn.cursor()

            def fetch(table):
                cur.execute(f"SELECT name FROM `{table}` WHERE is_deleted = 0")
                return [r[0] for r in cur.fetchall()]

            cur.execute("SELECT teacher, subject FROM teacher_expertise")
            expertise = {}
            for t, s in cur.fetchall():
                expertise.setdefault(t, []).append(s)

            cur.execute("SELECT name, email, phone FROM teachers WHERE is_deleted = 0")
            details = {r[0]: {"email": r[1] or "", "phone": r[2] or ""} for r in cur.fetchall()}

            self.data = {
                "teachers": fetch("teachers"), "subjects": fetch("subjects"),
                "classes": fetch("classes"), "classrooms": fetch("classrooms"),
                "lab_rooms": fetch("lab_rooms"), "teacher_expertise": expertise,
                "teacher_details": details,
            }

            cur.execute("SELECT class_name, day, period, subject, teacher, room FROM timetable_entries ORDER BY day, class_name, period")
            tt = {}
            for cls, day, period, sub, tch, room in cur.fetchall():
                tt.setdefault(day, {}).setdefault(cls, {})[period] = {"subject": sub, "teacher": tch, "room": room}
            self.generated_timetable = tt
            conn.close()
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc))
            self.data = {"teachers": [], "subjects": [], "classes": [], "classrooms": [], "lab_rooms": [], "teacher_expertise": {}, "teacher_details": {}}

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.navigation_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("#E2E8F0", "#09090C"))
        self.navigation_frame.grid(row=0, column=0, sticky="nsew")
        self.navigation_frame.grid_rowconfigure(20, weight=1)

        ctk.CTkLabel(self.navigation_frame, text="SCHEDULER PRO", font=ctk.CTkFont("Inter", 17, "bold"), text_color=TEXT_MAIN).pack(pady=(24, 6), padx=20)
        ctk.CTkLabel(self.navigation_frame, text="Academic Timetable System", font=("Inter", 10), text_color=TEXT_PALE).pack(pady=(0, 16), padx=20)
        ctk.CTkFrame(self.navigation_frame, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 12))

        for label, cmd in [
            ("  Dashboard", self.show_dashboard),
            ("  Manage Assets", self.show_manage),
            ("  Generate Schedule", self.show_generator),
            ("  View History", self.show_history),
            ("  Workload Analytics", self.show_analytics),
            ("  Recycle Bin", self.show_recycle_bin),
            ("  Teacher Details", self.show_teacher_details),
            ("  Teacher Feedback", self.show_feedback),
            ("  WhatsApp Hub", self.show_whatsapp_hub),
            ("  User Settings", self.show_user_settings),
            ("  Logout", self.show_login),
        ]:
            ctk.CTkButton(self.navigation_frame, text=label, font=("Inter", 13), anchor="w", fg_color="transparent", hover_color=("#CBD5E1", "#1E1E2A"), text_color=TEXT_MAIN, command=cmd, height=38, corner_radius=10).pack(pady=2, padx=12, fill="x")

        ctk.CTkFrame(self.navigation_frame, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=8)

        ctk.CTkButton(
            self.navigation_frame,
            text="🤖 AI Assistant (Mic)",
            font=("Inter", 14, "bold"),
            height=50, corner_radius=12,
            fg_color="#6366F1", hover_color="#4338CA",
            text_color="white",
            command=self.show_ai_assistant,
        ).pack(padx=16, pady=(0, 10), fill="x")

        self.mode_switch = ctk.CTkSwitch(self.navigation_frame, text="Dark Mode", command=lambda: self._sync_theme(self.mode_switch), font=("Inter", 12), text_color=TEXT_MAIN)
        self.mode_switch.pack(pady=(0, 20), padx=20, anchor="w")
        if ctk.get_appearance_mode() == "Dark":
            self.mode_switch.select()

        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew")
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

    def clear_main(self):
        for w in self.main_container.winfo_children():
            w.destroy()

    def _make_card(self, parent, **kwargs):
        defaults = dict(fg_color=BG_CARD, corner_radius=16, border_width=1, border_color=BORDER)
        defaults.update(kwargs)
        return ctk.CTkFrame(parent, **defaults)

    def _page_header(self, parent, title):
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 18))
        ctk.CTkLabel(hdr, text=title, font=("Inter", 26, "bold"), text_color=TEXT_MAIN).pack(side="left")
        return hdr

    def _sync_theme(self, source):
        new_mode = "Light" if ctk.get_appearance_mode() == "Dark" else "Dark"
        ctk.set_appearance_mode(new_mode)
        for sw in (getattr(self, "mode_switch", None), getattr(self, "login_mode_switch_ref", None)):
            if sw and sw is not source:
                sw.select() if new_mode == "Dark" else sw.deselect()

    def on_closing(self):
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM ai_history")
            conn.commit()
            conn.close()
        except Exception:
            pass
        self.destroy()

    def backup_database(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "w") as f:
                json.dump({"data": self.data, "timetable": self.generated_timetable}, f, indent=4)
            messagebox.showinfo("Done", f"Saved: {path}")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def voice_input(self, prompt_var, mic_btn, status_label):
        if not SR_AVAILABLE:
            messagebox.showerror("Mic Error", "pip install SpeechRecognition")
            return
        if not PYAUDIO_AVAILABLE:
            messagebox.showerror("PyAudio Missing", "pip install pyaudio")
            return
        if self._is_listening:
            return

        def _listen():
            self._is_listening = True
            self.after(0, lambda: mic_btn.configure(text="🔴 Sun raha hu...", fg_color=DANGER))
            self.after(0, lambda: status_label.configure(text="Ab bolo...", text_color=WARNING))
            try:
                r = sr.Recognizer()
                r.pause_threshold = 1.0
                with sr.Microphone() as source:
                    r.adjust_for_ambient_noise(source, duration=0.5)
                    audio = r.listen(source, timeout=8, phrase_time_limit=10)
                try:
                    text = r.recognize_google(audio, language="hi-IN")
                except Exception:
                    text = r.recognize_google(audio, language="en-IN")
                self.after(0, lambda t=text: prompt_var.set(t))
                self.after(0, lambda: status_label.configure(text=f"✓ {text}", text_color=SUCCESS))
            except sr.WaitTimeoutError:
                self.after(0, lambda: status_label.configure(text="Timeout", text_color=DANGER))
            except sr.UnknownValueError:
                self.after(0, lambda: status_label.configure(text="Awaaz samajh nahi aayi", text_color=DANGER))
            except Exception as e:
                self.after(0, lambda: status_label.configure(text=f"Error: {e}", text_color=DANGER))
            finally:
                self._is_listening = False
                self.after(0, lambda: mic_btn.configure(text="🎤 Mic", fg_color="#6366F1"))

        threading.Thread(target=_listen, daemon=True).start()

    def show_login(self):
        self.clear_main()
        self.navigation_frame.grid_remove()
        self.main_container.grid_configure(column=0, columnspan=2)

        bg = ctk.CTkFrame(self.main_container, fg_color=BG_MAIN, corner_radius=0)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        card = self._make_card(bg, width=450, height=520)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        ctk.CTkLabel(card, text="SCHEDULER PRO", font=("Inter", 24, "bold"), text_color=TEXT_MAIN).pack(pady=(44, 4))
        ctk.CTkLabel(card, text="Academic Timetable System", font=("Inter", 11), text_color=TEXT_PALE).pack(pady=(0, 30))

        u_var, p_var = ctk.StringVar(), ctk.StringVar()
        ctk.CTkLabel(card, text="Username", font=("Inter", 12, "bold"), text_color=TEXT_PALE).pack(anchor="w", padx=55)
        u_entry = ctk.CTkEntry(card, textvariable=u_var, width=340, height=44, placeholder_text="admin", font=("Inter", 13))
        u_entry.pack(pady=(4, 14))
        u_entry.focus()
        ctk.CTkLabel(card, text="Password", font=("Inter", 12, "bold"), text_color=TEXT_PALE).pack(anchor="w", padx=55)
        p_entry = ctk.CTkEntry(card, textvariable=p_var, width=340, height=44, show="*", placeholder_text="admin123", font=("Inter", 13))
        p_entry.pack(pady=(4, 10))

        err = ctk.CTkLabel(card, text="", font=("Inter", 11), text_color=DANGER)
        err.pack(pady=(0, 8))

        def _login(event=None):
            u, p = u_var.get().strip(), p_var.get().strip()
            if not u or not p:
                err.configure(text="Fill all fields.")
                return
            try:
                conn = self.get_connection()
                cur = conn.cursor()
                cur.execute("SELECT role FROM users WHERE username = %s AND password = %s", (u, p))
                result = cur.fetchone()
                conn.close()
                if result:
                    self.current_user_role = result[0]
                    self.current_username = u
                    self.navigation_frame.grid()
                    self.main_container.grid_configure(column=1, columnspan=1)
                    self.show_dashboard()
                else:
                    err.configure(text="Invalid credentials.")
                    p_entry.delete(0, "end")
            except Exception as exc:
                messagebox.showerror("Error", str(exc))

        p_entry.bind("<Return>", _login)
        ctk.CTkButton(card, text="LOGIN", command=_login, fg_color=ACCENT, hover_color=ACCENT_HOVER, height=46, width=340, font=("Inter", 14, "bold"), corner_radius=12).pack(pady=(4, 18))

        self.login_mode_switch_ref = ctk.CTkSwitch(card, text="Dark Mode", command=lambda: self._sync_theme(self.login_mode_switch_ref), font=("Inter", 12), text_color=TEXT_PALE)
        self.login_mode_switch_ref.pack()
        if ctk.get_appearance_mode() == "Dark":
            self.login_mode_switch_ref.select()
        ctk.CTkLabel(card, text="Default: admin / admin123", font=("Inter", 10), text_color=TEXT_PALE).pack(pady=(12, 20))

    def show_dashboard(self):
        self.clear_main()
        self.load_data()
        frame = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.pack(fill="x", pady=(16, 22), padx=6)
        hour = datetime.now().hour
        greet = "Good Morning" if hour < 12 else ("Good Afternoon" if hour < 17 else "Good Evening")
        ctk.CTkLabel(hdr, text=f"{greet}, {self.current_username}", font=("Inter", 26, "bold"), text_color=TEXT_MAIN).pack(side="left")
        ctk.CTkLabel(hdr, text=datetime.now().strftime("%A, %d %B %Y"), font=("Inter", 13), text_color=TEXT_PALE).pack(side="right", pady=6)

        kpi = ctk.CTkFrame(frame, fg_color="transparent")
        kpi.pack(fill="x", padx=4, pady=(0, 20))
        room_count = len(self.data.get("classrooms", [])) + len(self.data.get("lab_rooms", []))
        for label, value, color in [
            ("Teachers", len(self.data.get("teachers", [])), "#6366F1"),
            ("Subjects", len(self.data.get("subjects", [])), "#06B6D4"),
            ("Classes", len(self.data.get("classes", [])), SUCCESS),
            ("Rooms", room_count, WARNING),
            ("TT Days", len(self.generated_timetable), "#A78BFA"),
        ]:
            kc = self._make_card(kpi)
            kc.pack(side="left", expand=True, fill="both", padx=5)
            ctk.CTkLabel(kc, text=str(value), font=("Inter", 32, "bold"), text_color=color).pack(pady=(18, 2))
            ctk.CTkLabel(kc, text=label, font=("Inter", 12), text_color=TEXT_PALE).pack(pady=(0, 18))

        ctk.CTkLabel(frame, text="Quick Actions", font=("Inter", 16, "bold"), text_color=TEXT_MAIN).pack(anchor="w", padx=8, pady=(0, 10))
        qa = ctk.CTkFrame(frame, fg_color="transparent")
        qa.pack(fill="x", padx=4, pady=(0, 22))
        for lbl, cmd, col in [
            ("Generate Timetable", self.show_generator, ACCENT[1]),
            ("Manage Assets", self.show_manage, "#06B6D4"),
            ("View Analytics", self.show_analytics, SUCCESS),
            ("Backup Data", self.backup_database, WARNING),
        ]:
            ctk.CTkButton(qa, text=lbl, command=cmd, fg_color=col, hover_color=col, font=("Inter", 13, "bold"), height=48, corner_radius=12).pack(side="left", expand=True, fill="x", padx=5)

        info = self._make_card(frame)
        info.pack(fill="x", padx=4)
        ctk.CTkLabel(info, text="System Overview", font=("Inter", 15, "bold"), text_color=TEXT_MAIN).pack(anchor="w", padx=22, pady=(18, 8))
        exp = sum(len(v) for v in self.data.get("teacher_expertise", {}).values())
        mic_status = "✅ Mic Ready" if (SR_AVAILABLE and PYAUDIO_AVAILABLE) else "❌ Mic NOT ready"
        twilio_status = "✅ Twilio Ready" if TWILIO_AVAILABLE else "❌ pip install twilio"

        for line in [
            f"  Teacher-Subject links : {exp}",
            f"  Timetable days loaded  : {len(self.generated_timetable)}",
            f"  Logged-in role         : {(self.current_user_role or 'N/A').upper()}",
            f"  Mic Status             : {mic_status}",
            f"  Twilio Status          : {twilio_status}",
        ]:
            ctk.CTkLabel(info, text=line, font=("Inter", 13), text_color=TEXT_PALE, anchor="w").pack(anchor="w", padx=22, pady=2)
        ctk.CTkFrame(info, fg_color="transparent", height=16).pack()

    def show_manage(self):
        self.clear_main()
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._page_header(frame, "Manage Assets")

        cats = ["teachers", "subjects", "classes", "classrooms", "lab_rooms"]
        if self.current_manage_filter not in cats:
            self.current_manage_filter = cats[0]

        tab_bar = ctk.CTkFrame(frame, fg_color="transparent")
        tab_bar.pack(fill="x", pady=(0, 16))

        def _switch(cat):
            self.current_manage_filter = cat
            self.show_manage()

        for cat in cats:
            active = cat == self.current_manage_filter
            ctk.CTkButton(tab_bar, text=cat.replace("_", " ").title(), command=lambda c=cat: _switch(c),
                fg_color=ACCENT[1] if active else "transparent", hover_color=ACCENT_HOVER[1],
                text_color="white" if active else TEXT_MAIN,
                font=("Inter", 12, "bold" if active else "normal"),
                corner_radius=10, height=36, border_width=1,
                border_color=ACCENT[1] if active else BORDER).pack(side="left", padx=4)

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        left = self._make_card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        cat_label = self.current_manage_filter.replace("_", " ").title()
        ctk.CTkLabel(left, text=f"Add {cat_label}", font=("Inter", 15, "bold"), text_color=TEXT_MAIN).pack(pady=(22, 16), padx=22, anchor="w")

        name_var = ctk.StringVar()
        search_var = ctk.StringVar()

        name_entry = ctk.CTkEntry(left, textvariable=name_var, placeholder_text="Enter name...", height=42, font=("Inter", 13))
        name_entry.pack(padx=22, fill="x")
        name_entry.focus()

        msg_label = ctk.CTkLabel(left, text="", font=("Inter", 11))
        msg_label.pack(pady=6)

        def _add():
            val = name_var.get().strip()
            if not val:
                msg_label.configure(text="Empty.", text_color=DANGER)
                return
            tbl = self.current_manage_filter
            try:
                conn = self.get_connection()
                cur = conn.cursor()
                cur.execute(f"SELECT id, is_deleted FROM `{tbl}` WHERE name = %s", (val,))
                existing = cur.fetchone()
                if existing:
                    if existing[1] == 1:
                        cur.execute(f"UPDATE `{tbl}` SET is_deleted = 0 WHERE name = %s", (val,))
                        action = "Restored"
                    else:
                        msg_label.configure(text="Already exists.", text_color=WARNING)
                        conn.close()
                        return
                else:
                    cur.execute(f"INSERT INTO `{tbl}` (name) VALUES (%s)", (val,))
                    action = "Added"
                conn.commit()
                conn.close()
                self.load_data()
                name_var.set("")
                msg_label.configure(text=f"{action}: {val}", text_color=SUCCESS)
                _refresh_list()
            except Exception as exc:
                msg_label.configure(text=f"Error: {exc}", text_color=DANGER)

        name_entry.bind("<Return>", lambda _e: _add())
        ctk.CTkButton(left, text="Add Item", command=_add, fg_color=SUCCESS, hover_color="#16A34A", height=42, font=("Inter", 13, "bold"), corner_radius=10).pack(padx=22, pady=8, fill="x")

        ctk.CTkFrame(left, fg_color=BORDER, height=1).pack(fill="x", padx=22, pady=10)
        ctk.CTkLabel(left, text="Search", font=("Inter", 12), text_color=TEXT_PALE).pack(anchor="w", padx=22)
        search_var.trace_add("write", lambda *_: _refresh_list())
        ctk.CTkEntry(left, textvariable=search_var, placeholder_text="Search...", height=38).pack(padx=22, pady=(4, 8), fill="x")

        if self.current_manage_filter == "teachers":
            ctk.CTkFrame(left, fg_color=BORDER, height=1).pack(fill="x", padx=22, pady=8)
            ctk.CTkLabel(left, text="Set Teacher Expertise", font=("Inter", 13, "bold"), text_color=TEXT_MAIN).pack(padx=22, anchor="w", pady=(4, 6))

            teachers_list = self.data["teachers"] or ["No teachers"]
            teacher_var = ctk.StringVar(value=teachers_list[0])
            subject_vars = {}

            def _load_existing(*args):
                existing = self.data.get("teacher_expertise", {}).get(teacher_var.get(), [])
                for subj, var in subject_vars.items():
                    var.set(subj in existing)

            ctk.CTkOptionMenu(left, variable=teacher_var, values=teachers_list, height=36, command=lambda _: _load_existing()).pack(padx=22, pady=(0, 6), fill="x")

            exp_msg = ctk.CTkLabel(left, text="", font=("Inter", 11), wraplength=280)

            def _save_expertise():
                teacher = teacher_var.get()
                selected = [s for s, v in subject_vars.items() if v.get()]
                if not teacher or teacher == "No teachers":
                    exp_msg.configure(text="Select teacher.", text_color=DANGER)
                    return
                if not selected:
                    exp_msg.configure(text="Select subjects.", text_color=DANGER)
                    return
                try:
                    conn = self.get_connection()
                    cur = conn.cursor()
                    cur.execute("DELETE FROM teacher_expertise WHERE teacher = %s", (teacher,))
                    for s in selected:
                        cur.execute("INSERT INTO teacher_expertise (teacher, subject) VALUES (%s, %s)", (teacher, s))
                    conn.commit()
                    conn.close()
                    self.load_data()
                    exp_msg.configure(text=f"✓ Saved {len(selected)} subjects", text_color=SUCCESS)
                    _refresh_list()
                except Exception as exc:
                    exp_msg.configure(text=f"Error: {exc}", text_color=DANGER)

            ctk.CTkButton(left, text="💾  SAVE EXPERTISE", command=_save_expertise,
                fg_color=SUCCESS, hover_color="#16A34A", height=48,
                font=("Inter", 14, "bold"), corner_radius=10).pack(padx=22, pady=(8, 12), fill="x", side="bottom")
            exp_msg.pack(pady=(0, 6), side="bottom")

            subj_scroll = ctk.CTkScrollableFrame(left, fg_color=CARD_INNER, corner_radius=10)
            subj_scroll.pack(padx=22, pady=4, fill="both", expand=True)

            for subj in self.data.get("subjects", []):
                var = ctk.BooleanVar()
                subject_vars[subj] = var
                ctk.CTkCheckBox(subj_scroll, text=subj, variable=var, font=("Inter", 12), checkmark_color="white", fg_color=ACCENT[1]).pack(anchor="w", padx=8, pady=2)

            _load_existing()

        right = self._make_card(body)
        right.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(right, text=f"All {cat_label}", font=("Inter", 15, "bold"), text_color=TEXT_MAIN).pack(pady=(22, 8), padx=22, anchor="w")
        list_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        list_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        def _refresh_list():
            for w in list_scroll.winfo_children():
                w.destroy()
            q = search_var.get().strip().lower()
            items = self.data.get(self.current_manage_filter, [])
            shown = [i for i in items if q in i.lower()] if q else items
            if not shown:
                ctk.CTkLabel(list_scroll, text="No items.", font=("Inter", 13), text_color=TEXT_PALE).pack(pady=30)
                return
            for item in shown:
                row = ctk.CTkFrame(list_scroll, fg_color=CARD_INNER, corner_radius=10)
                row.pack(fill="x", pady=3, padx=4)
                badge = ""
                if self.current_manage_filter == "teachers":
                    subs = self.data["teacher_expertise"].get(item, [])
                    badge = f"  [{len(subs)}: {', '.join(subs[:3])}{'...' if len(subs) > 3 else ''}]" if subs else "  [0 subjects]"
                ctk.CTkLabel(row, text=f"  {item}{badge}", font=("Inter", 13), text_color=TEXT_MAIN, anchor="w").pack(side="left", padx=10, pady=10, fill="x", expand=True)
                ctk.CTkButton(row, text="Delete", width=68, height=30, fg_color=DANGER, hover_color="#B91C1C", font=("Inter", 12), corner_radius=8, command=lambda n=item: _del(n)).pack(side="right", padx=10, pady=8)

        def _del(name):
            if not messagebox.askyesno("Confirm", f"Delete '{name}'?"):
                return
            tbl = self.current_manage_filter
            try:
                conn = self.get_connection()
                cur = conn.cursor()
                cur.execute(f"UPDATE `{tbl}` SET is_deleted = 1 WHERE name = %s", (name,))
                conn.commit()
                conn.close()
                self.load_data()
                _refresh_list()
            except Exception as exc:
                messagebox.showerror("Error", str(exc))

        _refresh_list()

    def show_generator(self):
        self.clear_main()
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._page_header(frame, "Generate Timetable")

        cfg = self._make_card(frame)
        cfg.pack(fill="x", pady=(0, 14))
        row = ctk.CTkFrame(cfg, fg_color="transparent")
        row.pack(padx=22, pady=18, fill="x")
        ctk.CTkLabel(row, text="Periods/day:", font=("Inter", 12), text_color=TEXT_MAIN).grid(row=0, column=0, sticky="w", padx=(0, 8))
        periods_var = ctk.StringVar(value="8")
        ctk.CTkEntry(row, textvariable=periods_var, width=70, height=36).grid(row=0, column=1, sticky="w", padx=(0, 24))
        ctk.CTkLabel(row, text="Days:", font=("Inter", 12), text_color=TEXT_MAIN).grid(row=0, column=2, sticky="w", padx=(0, 8))
        days_var = ctk.StringVar(value="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday")
        ctk.CTkEntry(row, textvariable=days_var, width=360, height=36).grid(row=0, column=3, sticky="w")

        status = ctk.CTkLabel(frame, text="", font=("Inter", 13), text_color=TEXT_PALE)
        status.pack(anchor="w", padx=4, pady=(4, 0))
        progress = ctk.CTkProgressBar(frame, mode="indeterminate")

        result_card = self._make_card(frame)
        result_card.pack(fill="both", expand=True, pady=10)
        result_scroll = ctk.CTkScrollableFrame(result_card, fg_color="transparent")
        result_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        def _gen():
            teachers = self.data.get("teachers", [])
            subjects = self.data.get("subjects", [])
            classes = self.data.get("classes", [])
            classrooms = self.data.get("classrooms", [])
            expertise = self.data.get("teacher_expertise", {})
            if not teachers or not subjects or not classes:
                status.configure(text="Add teachers/subjects/classes.", text_color=DANGER)
                return
            try:
                n = int(periods_var.get())
            except Exception:
                status.configure(text="Invalid periods.", text_color=DANGER)
                return
            days = [d.strip() for d in days_var.get().split(",") if d.strip()]
            status.configure(text="Generating...", text_color=TEXT_PALE)
            progress.pack(fill="x", padx=4, pady=4)
            progress.start()

            def _work():
                tt = {}
                load = {t: 0 for t in teachers}
                try:
                    conn = self.get_connection()
                    cur = conn.cursor()
                    cur.execute("DELETE FROM timetable_entries")
                    for day in days:
                        tt[day] = {}
                        for cls in classes:
                            tt[day][cls] = {}
                            used = set()
                            for p in range(1, n + 1):
                                subj = random.choice(subjects)
                                elig = [t for t in teachers if subj in expertise.get(t, subjects) and t not in used]
                                if not elig:
                                    elig = [t for t in teachers if t not in used] or teachers
                                tch = random.choice(elig)
                                used.add(tch)
                                load[tch] += 1
                                room = random.choice(classrooms) if classrooms else "TBD"
                                tt[day][cls][p] = {"subject": subj, "teacher": tch, "room": room}
                                cur.execute("INSERT INTO timetable_entries (class_name, day, period, subject, teacher, room) VALUES (%s, %s, %s, %s, %s, %s)", (cls, day, p, subj, tch, room))
                    conn.commit()
                    conn.close()
                    self.generated_timetable = tt
                    self.load_data()
                    self.after(0, lambda: _show(tt))
                except Exception as exc:
                    self.after(0, lambda: status.configure(text=f"Error: {exc}", text_color=DANGER))
                finally:
                    self.after(0, lambda: (progress.stop(), progress.pack_forget()))

            threading.Thread(target=_work, daemon=True).start()

        ctk.CTkButton(frame, text="Generate Now", command=_gen, fg_color=ACCENT, hover_color=ACCENT_HOVER, height=46, font=("Inter", 14, "bold"), corner_radius=12).pack(anchor="w", padx=4, pady=(0, 8))

        def _show(tt):
            for w in result_scroll.winfo_children():
                w.destroy()
            status.configure(text=f"Generated {len(tt)} days.", text_color=SUCCESS)
            br = ctk.CTkFrame(result_scroll, fg_color="transparent")
            br.pack(anchor="w", pady=(0, 14))
            ctk.CTkButton(br, text="Export PDF", command=lambda: self.export_pdf(tt), fg_color=ACCENT, height=38, font=("Inter", 12, "bold"), corner_radius=10).pack(side="left", padx=(0, 8))
            ctk.CTkButton(br, text="Export Excel", command=lambda: self.export_excel(tt), fg_color=SUCCESS, height=38, font=("Inter", 12, "bold"), corner_radius=10).pack(side="left")
            for day, cls_data in tt.items():
                ctk.CTkLabel(result_scroll, text=f"  {day}", font=("Inter", 15, "bold"), text_color=ACCENT[1]).pack(anchor="w", pady=(14, 4), padx=6)
                for cls, periods in cls_data.items():
                    c = self._make_card(result_scroll)
                    c.pack(fill="x", pady=3, padx=4)
                    ctk.CTkLabel(c, text=f"  Class: {cls}", font=("Inter", 13, "bold"), text_color=TEXT_MAIN).pack(anchor="w", padx=14, pady=(10, 4))
                    for p, info in periods.items():
                        ctk.CTkLabel(c, text=f"    P{p}: {info['subject']} -- {info['teacher']} @ {info['room']}", font=("Inter", 12), text_color=TEXT_PALE).pack(anchor="w", padx=24, pady=1)
                    ctk.CTkFrame(c, fg_color="transparent", height=8).pack()

        if self.generated_timetable:
            _show(self.generated_timetable)

    def show_history(self):
        self.clear_main()
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._page_header(frame, "View History")
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT class_name, day, period, subject, teacher, room, created_at FROM timetable_entries ORDER BY created_at DESC LIMIT 200")
            rows = cur.fetchall()
            conn.close()
        except Exception as exc:
            ctk.CTkLabel(frame, text=str(exc), text_color=DANGER).pack()
            return
        if not rows:
            ctk.CTkLabel(frame, text="No history.", font=("Inter", 15), text_color=TEXT_PALE).pack(pady=60)
            return
        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, pady=4)
        for i, row in enumerate(rows):
            rf = ctk.CTkFrame(scroll, fg_color=BG_CARD if i % 2 == 0 else CARD_INNER, corner_radius=8)
            rf.pack(fill="x", pady=2)
            for val in row:
                ctk.CTkLabel(rf, text=str(val)[:20], font=("Inter", 11), text_color=TEXT_MAIN).pack(side="left", padx=8, pady=7)

    def show_analytics(self):
        self.clear_main()
        frame = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._page_header(frame, "Workload Analytics")
        load = {}
        for d in self.generated_timetable.values():
            for c in d.values():
                for e in c.values():
                    t = e.get("teacher", "")
                    if t:
                        load[t] = load.get(t, 0) + 1
        if not load:
            ctk.CTkLabel(frame, text="No data.", font=("Inter", 15), text_color=TEXT_PALE).pack(pady=60)
            return
        risks = self.ml_analyzer.predict_burnout({t: {"total": v, "max_consecutive": min(v // 2, 6)} for t, v in load.items()})
        mx = max(load.values(), default=1)
        for t, l in sorted(load.items(), key=lambda x: -x[1]):
            r = risks.get(t, 0)
            color = DANGER if r > 0.7 else (WARNING if r > 0.4 else SUCCESS)
            rc = self._make_card(frame)
            rc.pack(fill="x", pady=4)
            ctk.CTkLabel(rc, text=f"  {t}", font=("Inter", 13, "bold"), text_color=TEXT_MAIN, width=180, anchor="w").pack(side="left", padx=12, pady=14)
            bg = ctk.CTkFrame(rc, fg_color=CARD_INNER, corner_radius=8, height=20, width=300)
            bg.pack(side="left", padx=10, pady=14)
            bg.pack_propagate(False)
            ctk.CTkFrame(bg, fg_color=color, corner_radius=8, height=20, width=max(int(300 * l / mx), 4)).place(x=0, y=0)
            ctk.CTkLabel(rc, text=f"{l} periods", font=("Inter", 12), text_color=TEXT_PALE).pack(side="left", padx=8)
            ctk.CTkLabel(rc, text=f"Risk: {int(r * 100)}%", font=("Inter", 12, "bold"), text_color=color).pack(side="right", padx=16)

    def show_recycle_bin(self):
        self.clear_main()
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._page_header(frame, "Recycle Bin")
        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        def _ref():
            for w in scroll.winfo_children():
                w.destroy()
            found = False
            for tbl in ["teachers", "subjects", "classes", "classrooms", "lab_rooms"]:
                try:
                    conn = self.get_connection()
                    cur = conn.cursor()
                    cur.execute(f"SELECT name FROM `{tbl}` WHERE is_deleted = 1")
                    items = [r[0] for r in cur.fetchall()]
                    conn.close()
                except Exception:
                    continue
                if not items:
                    continue
                found = True
                ctk.CTkLabel(scroll, text=f"  {tbl.title()}", font=("Inter", 14, "bold"), text_color=TEXT_PALE).pack(anchor="w", pady=(14, 4))
                for name in items:
                    row = self._make_card(scroll)
                    row.pack(fill="x", pady=3)
                    ctk.CTkLabel(row, text=f"  {name}", font=("Inter", 13), text_color=TEXT_MAIN).pack(side="left", padx=14, pady=12)

                    def _r(n=name, t=tbl):
                        conn = self.get_connection()
                        cur = conn.cursor()
                        cur.execute(f"UPDATE `{t}` SET is_deleted = 0 WHERE name = %s", (n,))
                        conn.commit()
                        conn.close()
                        self.load_data()
                        _ref()

                    ctk.CTkButton(row, text="Restore", width=88, height=32, fg_color=SUCCESS, font=("Inter", 12), command=_r).pack(side="right", padx=6, pady=10)
            if not found:
                ctk.CTkLabel(scroll, text="Empty.", font=("Inter", 15), text_color=SUCCESS).pack(pady=60)

        _ref()

    def show_teacher_details(self):
        self.clear_main()
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._page_header(frame, "Teacher Details")

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        form = self._make_card(body)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ctk.CTkLabel(form, text="Add/Update", font=("Inter", 15, "bold"), text_color=TEXT_MAIN).pack(pady=(22, 16), padx=22, anchor="w")
        fields = {}
        for lbl in ("Name", "Email", "Phone"):
            ctk.CTkLabel(form, text=lbl, font=("Inter", 12), text_color=TEXT_PALE).pack(anchor="w", padx=22)
            v = ctk.StringVar()
            ctk.CTkEntry(form, textvariable=v, height=38, font=("Inter", 12)).pack(fill="x", padx=22, pady=(3, 12))
            fields[lbl.lower()] = v
        fm = ctk.CTkLabel(form, text="", font=("Inter", 11))
        fm.pack()

        def _save():
            n = fields["name"].get().strip()
            if not n:
                fm.configure(text="Name required.", text_color=DANGER)
                return
            try:
                conn = self.get_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO teachers (name, email, phone) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE email = VALUES(email), phone = VALUES(phone), is_deleted = 0", (n, fields["email"].get(), fields["phone"].get()))
                conn.commit()
                conn.close()
                self.load_data()
                fm.configure(text=f"Saved: {n}", text_color=SUCCESS)
                for v in fields.values():
                    v.set("")
                _r()
            except Exception as exc:
                fm.configure(text=str(exc), text_color=DANGER)

        ctk.CTkButton(form, text="Save", command=_save, fg_color=ACCENT, height=40, font=("Inter", 13, "bold"), corner_radius=10).pack(padx=22, pady=10, fill="x")

        tc = self._make_card(body)
        tc.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(tc, text="All Teachers", font=("Inter", 15, "bold"), text_color=TEXT_MAIN).pack(pady=(22, 8), padx=22, anchor="w")
        ts = ctk.CTkScrollableFrame(tc, fg_color="transparent")
        ts.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        def _r():
            for w in ts.winfo_children():
                w.destroy()
            for name, info in self.data.get("teacher_details", {}).items():
                c = self._make_card(ts)
                c.pack(fill="x", pady=4)
                ctk.CTkLabel(c, text=f"  {name}", font=("Inter", 13, "bold"), text_color=TEXT_MAIN).pack(anchor="w", padx=14, pady=(10, 3))
                ctk.CTkLabel(c, text=f"  Email: {info.get('email', 'N/A')}  |  Phone: {info.get('phone', 'N/A')}", font=("Inter", 12), text_color=TEXT_PALE).pack(anchor="w", padx=22, pady=(0, 10))

        _r()

    def show_feedback(self):
        self.clear_main()
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._page_header(frame, "Teacher Feedback")
        ctk.CTkLabel(frame, text="Feedback feature ready.", font=("Inter", 14), text_color=TEXT_PALE).pack(pady=40)

    # ═══════════════════════════════════════════════════════════════════════
    # ✅ WHATSAPP HUB WITH TWILIO API
    # ═══════════════════════════════════════════════════════════════════════
    def show_whatsapp_hub(self):
        self.clear_main()
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._page_header(frame, "📱 WhatsApp Hub (Twilio API)")

        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        teachers = self.data.get("teachers", [])
        t_var = ctk.StringVar(value=teachers[0] if teachers else "")

        # Twilio Credentials Card
        cred_card = self._make_card(scroll)
        cred_card.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(cred_card, text="🔑 Twilio API Credentials",
            font=("Inter", 15, "bold"), text_color=TEXT_MAIN).pack(anchor="w", padx=24, pady=(20, 4))

        if TWILIO_AVAILABLE:
            ctk.CTkLabel(cred_card, text="✅ Twilio Library Installed", font=("Inter", 11), text_color=SUCCESS).pack(anchor="w", padx=24, pady=(0, 10))
        else:
            ctk.CTkLabel(cred_card, text="❌ Run: pip install twilio", font=("Inter", 11), text_color=DANGER).pack(anchor="w", padx=24, pady=(0, 10))

        cred_file = "twilio_creds.json"
        saved = {}
        try:
            if os.path.exists(cred_file):
                with open(cred_file, "r") as f:
                    saved = json.load(f)
        except Exception:
            pass

        twilio_fields = {}
        for lbl, dflt, hidden, ph in [
            ("Account SID", saved.get("sid", ""), False, "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"),
            ("Auth Token", saved.get("token", ""), True, "Your auth token"),
            ("Twilio WhatsApp Number", saved.get("from", "+14155238886"), False, "+14155238886"),
        ]:
            ctk.CTkLabel(cred_card, text=lbl, font=("Inter", 12), text_color=TEXT_PALE).pack(anchor="w", padx=24)
            v = ctk.StringVar(value=dflt)
            ctk.CTkEntry(cred_card, textvariable=v, height=36, show="*" if hidden else "", placeholder_text=ph).pack(fill="x", padx=24, pady=(3, 8))
            twilio_fields[lbl] = v

        cred_status = ctk.CTkLabel(cred_card, text="", font=("Inter", 11))
        cred_status.pack()

        def _save_creds():
            try:
                creds = {
                    "sid": twilio_fields["Account SID"].get().strip(),
                    "token": twilio_fields["Auth Token"].get().strip(),
                    "from": twilio_fields["Twilio WhatsApp Number"].get().strip(),
                }
                with open(cred_file, "w") as f:
                    json.dump(creds, f)
                cred_status.configure(text="✅ Credentials saved!", text_color=SUCCESS)
            except Exception as exc:
                cred_status.configure(text=f"Error: {exc}", text_color=DANGER)

        ctk.CTkButton(cred_card, text="💾 Save Credentials", command=_save_creds,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, height=36,
            font=("Inter", 12, "bold"), corner_radius=10).pack(padx=24, pady=(8, 16), fill="x")

        # WhatsApp Message Card
        wa_card = self._make_card(scroll)
        wa_card.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(wa_card, text="📱 Send WhatsApp Message",
            font=("Inter", 15, "bold"), text_color=TEXT_MAIN).pack(anchor="w", padx=24, pady=(20, 14))

        ctk.CTkLabel(wa_card, text="Recipient Teacher:", font=("Inter", 12), text_color=TEXT_PALE).pack(anchor="w", padx=24)
        ctk.CTkOptionMenu(wa_card, variable=t_var, values=teachers or ["No teachers"], height=38).pack(fill="x", padx=24, pady=(4, 12))

        ctk.CTkLabel(wa_card, text="Phone (with +91):", font=("Inter", 12), text_color=TEXT_PALE).pack(anchor="w", padx=24)
        phone_var = ctk.StringVar()
        phone_entry = ctk.CTkEntry(wa_card, textvariable=phone_var, height=38, placeholder_text="+918253051016", font=("Inter", 12))
        phone_entry.pack(fill="x", padx=24, pady=(4, 12))

        def _auto_fill(*args):
            teacher = t_var.get()
            phone = self.data.get("teacher_details", {}).get(teacher, {}).get("phone", "")
            if phone:
                if not phone.startswith("+"):
                    phone = "+91" + phone.lstrip("0")
                phone_var.set(phone)

        t_var.trace_add("write", _auto_fill)
        _auto_fill()

        ctk.CTkLabel(wa_card, text="Message:", font=("Inter", 12), text_color=TEXT_PALE).pack(anchor="w", padx=24)
        wa_msg = ctk.CTkTextbox(wa_card, height=120, font=("Inter", 12))
        wa_msg.pack(fill="x", padx=24, pady=(4, 12))
        wa_msg.insert("1.0", "Hello! Your timetable has been updated. Please check Scheduler Pro portal.")

        wa_status = ctk.CTkLabel(wa_card, text="", font=("Inter", 11), wraplength=600)
        wa_status.pack(pady=4)

        def _send_whatsapp():
            if not TWILIO_AVAILABLE:
                wa_status.configure(text="❌ pip install twilio", text_color=DANGER)
                return
            sid = twilio_fields["Account SID"].get().strip()
            token = twilio_fields["Auth Token"].get().strip()
            from_num = twilio_fields["Twilio WhatsApp Number"].get().strip()
            to_num = phone_var.get().strip()
            message = wa_msg.get("1.0", "end").strip()

            if not sid or not token:
                wa_status.configure(text="❌ Credentials daalo!", text_color=DANGER)
                return
            if not to_num.startswith("+"):
                wa_status.configure(text="❌ Phone mein +91 lagao!", text_color=DANGER)
                return
            if not message:
                wa_status.configure(text="❌ Message likho!", text_color=DANGER)
                return

            wa_status.configure(text="⏳ Sending...", text_color=WARNING)

            def _worker():
                try:
                    client = TwilioClient(sid, token)
                    msg = client.messages.create(
                        from_=f"whatsapp:{from_num}",
                        body=message,
                        to=f"whatsapp:{to_num}"
                    )
                    self.after(0, lambda: wa_status.configure(
                        text=f"✅ Sent! SID: {msg.sid[:25]}...",
                        text_color=SUCCESS
                    ))
                except Exception as exc:
                    err = str(exc)
                    if "authenticate" in err.lower():
                        err = "Auth Token galat!"
                    elif "not a valid" in err.lower():
                        err = "Phone format galat!"
                    elif "63007" in err or "sandbox" in err.lower():
                        err = "Recipient ne sandbox join nahi kiya. Pehle 'join lovely-husband' bhejo +14155238886 par."
                    self.after(0, lambda e=err: wa_status.configure(text=f"❌ {e[:200]}", text_color=DANGER))

            threading.Thread(target=_worker, daemon=True).start()

        ctk.CTkButton(wa_card, text="📤 Send WhatsApp (Twilio)", command=_send_whatsapp,
            fg_color="#25D366", hover_color="#1DA851", height=44,
            font=("Inter", 14, "bold"), corner_radius=10).pack(padx=24, pady=(10, 12), fill="x")

        info_box = ctk.CTkFrame(wa_card, fg_color=CARD_INNER, corner_radius=10)
        info_box.pack(fill="x", padx=24, pady=(0, 16))
        info = (
            "ℹ️  Sandbox: join lovely-husband\n"
            "Number: +1 415 523 8886\n\n"
            "Recipient ko WhatsApp se 'join lovely-husband' bhejna hoga.\n"
            "💰 Trial: $14.33 (~2800 messages)"
        )
        ctk.CTkLabel(info_box, text=info, font=("Inter", 11), text_color=TEXT_PALE, justify="left").pack(padx=14, pady=10, anchor="w")

        # Email Card
        email_card = self._make_card(scroll)
        email_card.pack(fill="x")
        ctk.CTkLabel(email_card, text="📧 Send Email", font=("Inter", 15, "bold"), text_color=TEXT_MAIN).pack(anchor="w", padx=24, pady=(20, 14))

        ef = {}
        for lbl, dflt, h in [("SMTP Host", "smtp.gmail.com", False), ("SMTP Port", "587", False), ("Sender Email", "", False), ("App Password", "", True)]:
            ctk.CTkLabel(email_card, text=lbl, font=("Inter", 12), text_color=TEXT_PALE).pack(anchor="w", padx=24)
            v = ctk.StringVar(value=dflt)
            ctk.CTkEntry(email_card, textvariable=v, height=36, show="*" if h else "").pack(fill="x", padx=24, pady=(3, 8))
            ef[lbl] = v

        em_status = ctk.CTkLabel(email_card, text="", font=("Inter", 11))
        em_status.pack()

        def _send_email():
            to = self.data.get("teacher_details", {}).get(t_var.get(), {}).get("email", "")
            if not to:
                em_status.configure(text="No email.", text_color=DANGER)
                return
            try:
                m = MIMEMultipart()
                m["From"] = ef["Sender Email"].get()
                m["To"] = to
                m["Subject"] = "Timetable Update"
                m.attach(MIMEText(wa_msg.get("1.0", "end").strip(), "plain"))
                with smtplib.SMTP(ef["SMTP Host"].get(), int(ef["SMTP Port"].get())) as srv:
                    srv.starttls()
                    srv.login(ef["Sender Email"].get(), ef["App Password"].get())
                    srv.sendmail(ef["Sender Email"].get(), to, m.as_string())
                em_status.configure(text=f"✅ Sent to {to}", text_color=SUCCESS)
            except Exception as exc:
                em_status.configure(text=str(exc), text_color=DANGER)

        ctk.CTkButton(email_card, text="📧 Send Email", command=_send_email, fg_color=ACCENT, height=40, font=("Inter", 13, "bold"), corner_radius=10).pack(padx=24, pady=10, fill="x")
        ctk.CTkFrame(email_card, fg_color="transparent", height=10).pack()

    def show_user_settings(self):
        self.clear_main()
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._page_header(frame, "User Settings")
        ctk.CTkLabel(frame, text=f"Logged in: {self.current_username} ({self.current_user_role})", font=("Inter", 14), text_color=TEXT_PALE).pack(pady=40)

    def show_ai_assistant(self):
        if self._ai_win and self._ai_win.winfo_exists():
            self._ai_win.focus()
            return

        win = ctk.CTkToplevel(self)
        win.title("🤖 AI Assistant with Mic")
        win.geometry("720x780")
        win.configure(fg_color=BG_MAIN)
        self._ai_win = win

        ctk.CTkLabel(win, text="🤖 AI Assistant", font=("Inter", 22, "bold"), text_color=ACCENT[1]).pack(pady=(20, 4))

        mic_text = "Type karein ya 🎤 Mic dabakar bolein"
        if not PYAUDIO_AVAILABLE:
            mic_text = "⚠️ pip install pyaudio | Text type karein"
        ctk.CTkLabel(win, text=mic_text, font=("Inter", 11), text_color=TEXT_PALE).pack(pady=(0, 12))

        chat = ctk.CTkScrollableFrame(win, fg_color=BG_CARD, corner_radius=12)
        chat.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        def _bubble(role, text):
            user = role == "user"
            o = ctk.CTkFrame(chat, fg_color="transparent")
            o.pack(fill="x", pady=4, padx=6)
            b = ctk.CTkFrame(o, fg_color=ACCENT[1] if user else CARD_INNER, corner_radius=14)
            b.pack(anchor="e" if user else "w")
            ctk.CTkLabel(b, text=text, wraplength=540, font=("Inter", 12), text_color="white" if user else TEXT_MAIN, justify="left").pack(padx=16, pady=10)

        try:
            conn = self.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT role, content FROM ai_history ORDER BY created_at ASC LIMIT 40")
            for r, c in cur.fetchall():
                _bubble(r, c)
            conn.close()
        except Exception:
            pass

        vs = ctk.CTkLabel(win, text="", font=("Inter", 11), text_color=WARNING)
        vs.pack(pady=(0, 4))

        ir = ctk.CTkFrame(win, fg_color="transparent")
        ir.pack(fill="x", padx=20, pady=(0, 4))

        pv = ctk.StringVar()
        pe = ctk.CTkEntry(ir, textvariable=pv, placeholder_text="Type ya 🎤 Mic dabao...", height=44, font=("Inter", 13))
        pe.pack(side="left", fill="x", expand=True, padx=(0, 6))
        pe.focus()

        mic_btn = ctk.CTkButton(ir, text="🎤 Mic", width=85, height=44, font=("Inter", 13, "bold"), corner_radius=10, fg_color="#6366F1", hover_color=ACCENT_HOVER, command=lambda: self.voice_input(pv, mic_btn, vs))
        mic_btn.pack(side="left", padx=(0, 6))

        tl = ctk.CTkLabel(win, text="", font=("Inter", 11), text_color=TEXT_PALE)
        tl.pack(pady=(0, 8))

        def _s(event=None):
            p = pv.get().strip()
            if not p:
                return
            pv.set("")
            _bubble("user", p)
            try:
                conn = self.get_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO ai_history (role, content) VALUES (%s, %s)", ("user", p))
                conn.commit()
                conn.close()
            except Exception:
                pass
            tl.configure(text="AI soch raha hai...")

            def _w():
                ctx = {**self.data, "generated_timetable": self.generated_timetable}
                resp = self.ai.ask(p, ctx)
                try:
                    conn = self.get_connection()
                    cur = conn.cursor()
                    cur.execute("INSERT INTO ai_history (role, content) VALUES (%s, %s)", ("assistant", resp))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
                self.after(0, lambda: (_bubble("assistant", resp), tl.configure(text="")))

            threading.Thread(target=_w, daemon=True).start()

        pe.bind("<Return>", _s)
        ctk.CTkButton(ir, text="Send", command=_s, fg_color=ACCENT, hover_color=ACCENT_HOVER, height=44, width=80, font=("Inter", 13, "bold"), corner_radius=10).pack(side="right")

    def export_pdf(self, timetable):
        if not FPDF_AVAILABLE:
            messagebox.showerror("Missing", "pip install fpdf2")
            return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 12, "Timetable", ln=True, align="C")
            pdf.set_font("Helvetica", "", 10)
            for day, cls_data in timetable.items():
                pdf.set_font("Helvetica", "B", 12)
                pdf.cell(0, 8, day, ln=True)
                pdf.set_font("Helvetica", "", 10)
                for cls, periods in cls_data.items():
                    pdf.cell(0, 6, f"  Class: {cls}", ln=True)
                    for p, info in periods.items():
                        pdf.cell(0, 6, f"    P{p}: {info['subject']} | {info['teacher']} | {info['room']}", ln=True)
            pdf.output(path)
            messagebox.showinfo("Done", f"Saved: {path}")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def export_excel(self, timetable):
        if not PANDAS_AVAILABLE:
            messagebox.showerror("Missing", "pip install pandas openpyxl")
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            rows = []
            for day, cls_data in timetable.items():
                for cls, periods in cls_data.items():
                    for p, info in periods.items():
                        rows.append({"Day": day, "Class": cls, "Period": p, "Subject": info["subject"], "Teacher": info["teacher"], "Room": info["room"]})
            pd.DataFrame(rows).to_excel(path, index=False)
            messagebox.showinfo("Done", f"Saved: {path}")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))


if __name__ == "__main__":
    app = TimetableApp()
    app.mainloop()