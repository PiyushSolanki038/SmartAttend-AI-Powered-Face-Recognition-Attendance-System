from tkinter import filedialog, messagebox

import customtkinter as ctk

from db import queries
from services import report
from services.session import SessionController, close_day
from ui.components.toast import show_toast
from ui.components.video_feed import VideoFeed

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

        bottom_bar = ctk.CTkFrame(self._live_frame, fg_color="transparent")
        bottom_bar.pack(fill="x", padx=10, pady=10)
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

            for name in newly_recognized:
                _beep(present=True)
                show_toast(self, f"Marked Present: {name}", "success")

        self._poll_job = self.after(100, self._poll_frame)

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

    def _close_day(self):
        if not messagebox.askyesno("Close Day", "This will mark every enrolled student not yet seen today as absent, "
                                                 "across all branches. Continue?"):
            return
        session_id = close_day()
        if session_id is None:
            show_toast(self, "No open day to close.", "warning")
            return
        messagebox.showinfo("Day Closed", f"Day closed (session #{session_id}). Absentees finalized across all branches.")
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
