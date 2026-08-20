from datetime import date
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk

from db import queries
from services import attendance as attendance_service
from services import qr_checkin
from services import report
from services.announcements import AnnouncementError, create_announcement
from services.session import SessionController, close_day
from services.sessions import SessionAssignError, assign_substitute_faculty
from ui.components.toast import show_toast
from ui.components.video_feed import VideoFeed

try:
    import qrcode
    _HAS_QRCODE = True
except Exception:
    _HAS_QRCODE = False

try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False


def _beep(present: bool):
    if not _HAS_WINSOUND:
        return
    try:
        winsound.Beep(1000 if present else 400, 150)
    except RuntimeError:
        pass


class SessionScreen(ctk.CTkFrame):
    """Always-on Live Attendance screen. No subject/section/faculty setup — the camera starts
    automatically as soon as this screen is opened, and every recognized student is routed
    into today's auto-attendance record under their own enrolled branch."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.controller = None
        self._poll_job = None

        self._build_live_view()
        self._live_frame.pack(fill="both", expand=True)

    def _build_live_view(self):
        self._live_frame = ctk.CTkFrame(self)

        top_bar = ctk.CTkFrame(self._live_frame, fg_color="transparent")
        top_bar.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(top_bar, text="Live Attendance", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        self.status_text = ctk.CTkLabel(top_bar, text="Starting camera...", font=ctk.CTkFont(size=12), text_color="#AAAAAA")
        self.status_text.pack(side="left", padx=15)

        self.pause_btn = ctk.CTkButton(top_bar, text="Pause Watching", width=120, command=self._toggle_pause)
        self.pause_btn.pack(side="right", padx=5)
        ctk.CTkButton(top_bar, text="Close Day", fg_color="#E74C3C", hover_color="#C0392B", command=self._close_day).pack(side="right", padx=5)
        ctk.CTkButton(top_bar, text="Assign Substitute", command=self._assign_substitute).pack(side="right", padx=5)

        picker_bar = ctk.CTkFrame(self._live_frame, fg_color="transparent")
        picker_bar.pack(fill="x", padx=10, pady=(0, 5))
        ctk.CTkLabel(picker_bar, text="Active Session (for QR / Substitute / Bulk Mark / Flag Present):").pack(side="left")
        self.session_picker = ctk.CTkOptionMenu(picker_bar, values=["-- No Open Sessions --"], width=320)
        self.session_picker.pack(side="left", padx=10)
        self._session_picker_map = {}  # display string -> session_id

        badge_bar = ctk.CTkFrame(self._live_frame, fg_color="transparent")
        badge_bar.pack(fill="x", padx=10)
        self.present_badge = self._make_badge(badge_bar, "Present: 0", "#2ECC71")
        self.unknown_badge = self._make_badge(badge_bar, "Unknown: 0", "#F39C12")
        self.spoof_badge = self._make_badge(badge_bar, "Spoof: 0", "#9B59B6")
        self.total_badge = self._make_badge(badge_bar, "Enrolled: 0", "#1F6AA5")

        body = ctk.CTkFrame(self._live_frame, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10)

        left = ctk.CTkFrame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.video_feed = VideoFeed(left, width=640, height=480)
        self.video_feed.pack(padx=10, pady=10)
        self.status_label = ctk.CTkLabel(left, text="Faces: 0")
        self.status_label.pack(pady=5)

        right = ctk.CTkFrame(body, width=280)
        right.pack(side="left", fill="y")
        self.present_label = ctk.CTkLabel(right, text="PRESENT TODAY (0)", font=ctk.CTkFont(weight="bold"))
        self.present_label.pack(anchor="w", padx=10, pady=(10, 0))
        self.present_box = ctk.CTkTextbox(right, width=260, height=220)
        self.present_box.pack(padx=10, pady=10)
        self.unknown_label = ctk.CTkLabel(right, text="UNKNOWN (0)")
        self.unknown_label.pack(anchor="w", padx=10)

        ctk.CTkLabel(right, text="Manual Override", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(15, 0))
        self.override_dropdown = ctk.CTkOptionMenu(right, values=["-- Select Student --"])
        self.override_dropdown.pack(padx=10, pady=5, fill="x")
        override_btns = ctk.CTkFrame(right, fg_color="transparent")
        override_btns.pack(padx=10, pady=5, fill="x")
        ctk.CTkButton(override_btns, text="Mark Present", fg_color="#2ECC71", width=110, command=lambda: self._manual_override("manual")).pack(side="left", padx=(0, 5))
        ctk.CTkButton(override_btns, text="Mark Absent", fg_color="#E74C3C", width=110, command=lambda: self._manual_override("absent")).pack(side="left")
        ctk.CTkButton(override_btns, text="Flag as Present", fg_color="#1F6AA5", width=110, command=self._flag_present_selected).pack(side="left", padx=(5, 0))

        ctk.CTkLabel(right, text="Bulk Mark (comma-separated student IDs)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(15, 0))
        self.bulk_entry = ctk.CTkEntry(right, placeholder_text="1,2,3")
        self.bulk_entry.pack(padx=10, pady=5, fill="x")
        bulk_btns = ctk.CTkFrame(right, fg_color="transparent")
        bulk_btns.pack(padx=10, pady=5, fill="x")
        ctk.CTkButton(bulk_btns, text="Bulk Present", fg_color="#2ECC71", width=110, command=lambda: self._bulk_mark("present")).pack(side="left", padx=(0, 5))
        ctk.CTkButton(bulk_btns, text="Bulk Absent", fg_color="#E74C3C", width=110, command=lambda: self._bulk_mark("absent")).pack(side="left")

        bottom_bar = ctk.CTkFrame(self._live_frame, fg_color="transparent")
        bottom_bar.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(bottom_bar, text="Show QR Check-in", command=self._show_qr).pack(side="left")
        ctk.CTkButton(bottom_bar, text="Send Announcement", command=self._send_announcement).pack(side="left", padx=5)
        ctk.CTkButton(bottom_bar, text="Export Now", command=self._export_now).pack(side="right")

    def _make_badge(self, parent, text, color):
        badge = ctk.CTkLabel(parent, text=text, fg_color=color, text_color="white", corner_radius=6, width=120, height=28, font=ctk.CTkFont(weight="bold"))
        badge.pack(side="left", padx=5, pady=5)
        return badge

    def on_show(self):
        if self.controller is not None:
            return  # already watching — resume in place, don't restart the camera

        self.controller = SessionController()
        user_id = self.app.current_user["id"] if self.app.current_user else None
        if not self.controller.start(user_id):
            messagebox.showerror("Camera Error", "No webcam detected. Please connect a camera and try again.")
            self.controller = None
            self.status_text.configure(text="No camera detected")
            return

        self._student_lookup = {s["id"]: s["name"] for s in queries.list_students()}
        self.override_dropdown.configure(values=[f"{sid} - {name}" for sid, name in self._student_lookup.items()] or ["-- No Students --"])
        if self._student_lookup:
            first_key = next(iter(self._student_lookup))
            self.override_dropdown.set(f"{first_key} - {self._student_lookup[first_key]}")

        self.total_badge.configure(text=f"Enrolled: {self.controller.total_enrolled}")
        self.status_text.configure(text="Watching — attendance is recorded automatically")
        self.pause_btn.configure(text="Pause Watching")
        self._refresh_session_picker()
        self._poll_frame()

    def _toggle_pause(self):
        if self.controller is None:
            return
        paused = self.controller.toggle_pause()
        self.pause_btn.configure(text="Resume Watching" if paused else "Pause Watching")
        self.status_text.configure(text="Paused" if paused else "Watching — attendance is recorded automatically")

    def pause_for_external_camera_use(self):
        """Releases the webcam so another screen (Enroll's face scan) can use it without
        contention. Only one process can hold the camera device at a time."""
        self._stop_watching()
        self.status_text.configure(text="Paused — camera in use elsewhere")

    def refresh_encodings(self):
        if self.controller is not None:
            self.controller.refresh_encodings()
            self.total_badge.configure(text=f"Enrolled: {self.controller.total_enrolled}")

    def resume_after_external_camera_use(self):
        if self.controller is None:
            self.on_show()

    def _poll_frame(self):
        if self.controller is None:
            return
        frame, face_count, newly_recognized = self.controller.process_next_frame()

        if frame is not None:
            self.video_feed.update_frame(frame)
            self.status_label.configure(text=f"Faces: {face_count}" + (" (Paused)" if self.controller.paused else ""))
            self.present_box.delete("1.0", "end")
            for name in self.controller.present_students.values():
                self.present_box.insert("end", f"✓ {name}\n")
            self.present_label.configure(text=f"PRESENT TODAY ({len(self.controller.present_students)})")
            self.unknown_label.configure(text=f"UNKNOWN ({self.controller.unknown_count})")
            self.present_badge.configure(text=f"Present: {len(self.controller.present_students)}")
            self.unknown_badge.configure(text=f"Unknown: {self.controller.unknown_count}")
            self.spoof_badge.configure(text=f"Spoof: {self.controller.spoof_count}")

            for name, subject, section in newly_recognized:
                _beep(present=True)
                label = f"{subject} ({section})" if subject and section else (subject or "General")
                show_toast(self, f"Marked Present: {name} — {label}", "success")

            if newly_recognized:
                self._refresh_session_picker()

        self._poll_job = self.after(100, self._poll_frame)

    def _refresh_session_picker(self):
        """Populates the Active Session picker from today's currently-open sessions, since the
        camera can have multiple concurrent subject sessions open at once — faculty must pick
        which one the QR/Substitute/Bulk Mark/Flag Present actions should act on rather than
        relying on whichever student was last recognized (which may belong to a different class)."""
        today = date.today().isoformat()
        open_sessions = queries.list_open_sessions_today(today)
        self._session_picker_map = {}
        display_values = []
        for sess in open_sessions:
            label = f"#{sess['id']} — {sess['subject'] or 'General'}"
            if sess["section"]:
                label += f" ({sess['section']})"
            display_values.append(label)
            self._session_picker_map[label] = sess["id"]
        if not display_values:
            display_values = ["-- No Open Sessions --"]
        current = self.session_picker.get()
        self.session_picker.configure(values=display_values)
        if current not in display_values:
            self.session_picker.set(display_values[0])

    def _selected_session_id(self):
        """The session id chosen in the Active Session picker, or the controller's last-resolved
        session as a fallback if nothing has been explicitly picked yet."""
        selection = self.session_picker.get()
        if selection in self._session_picker_map:
            return self._session_picker_map[selection]
        return self.controller.session_id if self.controller is not None else None

    def _manual_override(self, status: str):
        if self.controller is None:
            return
        selection = self.override_dropdown.get()
        if " - " not in selection:
            return
        student_id = int(selection.split(" - ")[0])
        self.controller.manual_override(student_id, status)
        kind = "success" if status in ("present", "manual") else "warning"
        show_toast(self, f"{self._student_lookup.get(student_id, 'Student')} marked {status}", kind)

    def _flag_present_selected(self):
        if self.controller is None:
            return
        selection = self.override_dropdown.get()
        if " - " not in selection:
            return
        student_id = int(selection.split(" - ")[0])
        actor_id = self.app.current_user["id"] if self.app.current_user else None
        session_id = self._selected_session_id()
        if session_id is None:
            show_toast(self, "No active session", "warning")
            return
        attendance_service.flag_present(session_id, student_id, actor_id)
        show_toast(self, f"{self._student_lookup.get(student_id, 'Student')} flagged present", "success")

    def _bulk_mark(self, status: str):
        if self.controller is None:
            return
        session_id = self._selected_session_id()
        if session_id is None:
            show_toast(self, "No active session", "warning")
            return
        raw = self.bulk_entry.get().strip()
        if not raw:
            show_toast(self, "Enter comma-separated student IDs", "warning")
            return
        try:
            student_ids = [int(x.strip()) for x in raw.split(",") if x.strip()]
        except ValueError:
            messagebox.showerror("Invalid Input", "Student IDs must be numbers separated by commas.")
            return
        actor_id = self.app.current_user["id"] if self.app.current_user else None
        try:
            attendance_service.bulk_mark_attendance(session_id, student_ids, status, actor_id)
        except attendance_service.AttendanceError as e:
            messagebox.showerror("Bulk Mark Failed", str(e))
            return
        show_toast(self, f"{len(student_ids)} student(s) marked {status}", "success")

    def _show_qr(self):
        if self.controller is None:
            show_toast(self, "No active session", "warning")
            return
        session_id = self._selected_session_id()
        if session_id is None:
            show_toast(self, "No active session", "warning")
            return
        token = qr_checkin.generate_qr_token(session_id)
        if not _HAS_QRCODE:
            messagebox.showinfo("QR Token", f"qrcode package not installed. Token: {token}")
            return
        img = qrcode.make(f"/checkin/qr/{token}")
        top = ctk.CTkToplevel(self)
        top.title("QR Self Check-in")
        from PIL import ImageTk
        photo = ImageTk.PhotoImage(img.resize((260, 260)))
        label = ctk.CTkLabel(top, image=photo, text="")
        label.image = photo
        label.pack(padx=20, pady=20)

    def _send_announcement(self):
        subject = simpledialog.askstring("Announcement", "Subject:", parent=self)
        if not subject:
            return
        body = simpledialog.askstring("Announcement", "Message:", parent=self)
        if not body:
            return
        institution_wide = messagebox.askyesno("Scope", "Send to the whole institution? (No = department-only)")
        actor_id = self.app.current_user["id"] if self.app.current_user else None
        department = None
        if not institution_wide:
            department = simpledialog.askstring("Department", "Department to notify:", parent=self)
        try:
            _, sent = create_announcement(actor_id, subject, body, department=department,
                                           is_institution_wide=institution_wide)
        except AnnouncementError as e:
            messagebox.showerror("Error", str(e))
            return
        show_toast(self, f"Announcement sent (emailed {len(sent)} student(s))", "success")

    def _assign_substitute(self):
        if self.controller is None:
            show_toast(self, "No active session", "warning")
            return
        session_id = self._selected_session_id()
        if session_id is None:
            show_toast(self, "No active session", "warning")
            return
        staff = queries.list_staff_users()
        if not staff:
            show_toast(self, "No staff accounts to assign", "warning")
            return
        choice = simpledialog.askstring(
            "Assign Substitute Faculty",
            "Enter the username of the substitute:\n" + ", ".join(u["username"] for u in staff),
            parent=self,
        )
        if not choice:
            return
        match = next((u for u in staff if u["username"] == choice.strip()), None)
        if match is None:
            messagebox.showerror("Not Found", "No staff account with that username.")
            return
        actor_id = self.app.current_user["id"] if self.app.current_user else None
        try:
            assign_substitute_faculty(session_id, match["id"], actor_id)
        except SessionAssignError as e:
            messagebox.showerror("Error", str(e))
            return
        show_toast(self, f"Substitute assigned: {match['username']}", "success")

    def _close_day(self):
        if not messagebox.askyesno("Close Day", "This will mark every enrolled student not yet seen as absent, "
                                                 "across every subject/period held today. Continue?"):
            return
        session_ids = close_day()
        if not session_ids:
            show_toast(self, "No open sessions to close.", "warning")
            return
        messagebox.showinfo("Day Closed", f"{len(session_ids)} session(s) closed. Absentees finalized per subject/period.")
        self._refresh_session_picker()
        self._stop_watching()

    def _stop_watching(self):
        if self.controller is not None:
            if self._poll_job is not None:
                self.after_cancel(self._poll_job)
                self._poll_job = None
            self.controller.stop_watching()
            self.controller = None
            self.status_text.configure(text="Stopped — reopen this screen to resume watching")

    def _export_now(self):
        if self.controller is None:
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if not filepath:
            return
        try:
            report.export_excel(filepath)
            show_toast(self, f"Saved to {filepath}", "success")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def on_close(self):
        self._stop_watching()
