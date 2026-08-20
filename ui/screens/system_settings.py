"""Admin-only system health/config screen: camera status test, confidence threshold
slider (persisted via app_settings, not config.json — this is a DB-backed runtime knob
distinct from Settings screen's local config), and DB backup/restore."""

from tkinter import filedialog, messagebox

import cv2
import customtkinter as ctk

import config
from services import backup_scheduler
from services.settings import get_setting, set_setting
from ui.components.toast import show_toast


class SystemSettingsScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkButton(header, text="< Back", width=80, command=lambda: self.app.show_screen("HomeScreen")).pack(side="left")
        ctk.CTkLabel(header, text="System Health & Config", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=20)

        health = ctk.CTkFrame(self)
        health.pack(padx=20, pady=10, fill="x")
        ctk.CTkLabel(health, text="Camera Status", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.camera_status_label = ctk.CTkLabel(health, text="Not tested")
        self.camera_status_label.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        ctk.CTkButton(health, text="Test Camera", command=self._test_camera).grid(row=0, column=2, padx=10, pady=10)

        ctk.CTkLabel(health, text="Confidence Threshold").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.threshold_slider = ctk.CTkSlider(health, from_=0.3, to=0.9, number_of_steps=60, command=self._on_threshold_change)
        self.threshold_slider.set(float(get_setting("confidence_threshold", config.TOLERANCE)))
        self.threshold_slider.grid(row=1, column=1, padx=10, pady=10)
        self.threshold_value = ctk.CTkLabel(health, text="")
        self.threshold_value.grid(row=1, column=2, padx=10, pady=10)
        self._on_threshold_change(self.threshold_slider.get())

        backup = ctk.CTkFrame(self)
        backup.pack(padx=20, pady=10, fill="x")
        ctk.CTkLabel(backup, text="Database Backup / Restore", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 4), sticky="w")
        self.last_backup_label = ctk.CTkLabel(backup, text="")
        self.last_backup_label.grid(row=1, column=0, columnspan=3, padx=10, sticky="w")
        ctk.CTkButton(backup, text="Backup Now", command=self._backup_now).grid(row=2, column=0, padx=10, pady=10)
        ctk.CTkButton(backup, text="Restore From File...", fg_color="#E74C3C", hover_color="#C0392B",
                      command=self._restore).grid(row=2, column=1, padx=10, pady=10)

        ctk.CTkLabel(backup, text="Auto-backup interval (hours, while app is open)").grid(row=3, column=0, padx=10, pady=(10, 4), sticky="w")
        self.interval_entry = ctk.CTkEntry(backup, width=80)
        self.interval_entry.insert(0, str(get_setting("backup_interval_hours", backup_scheduler.BACKUP_INTERVAL_HOURS_DEFAULT)))
        self.interval_entry.grid(row=3, column=1, padx=10, pady=(10, 4), sticky="w")
        ctk.CTkButton(backup, text="Save Interval", command=self._save_interval).grid(row=3, column=2, padx=10, pady=(10, 4))

    def on_show(self):
        last = get_setting("last_backup_at", "never")
        self.last_backup_label.configure(text=f"Last backup: {last}")

    def _test_camera(self):
        cap = cv2.VideoCapture(config.CAMERA_INDEX)
        ok = cap.isOpened()
        cap.release()
        self.camera_status_label.configure(text="OK" if ok else "Not detected", text_color="#2ECC71" if ok else "#E74C3C")

    def _on_threshold_change(self, value):
        self.threshold_value.configure(text=f"{value:.2f}")
        set_setting("confidence_threshold", round(value, 2))

    def _backup_now(self):
        try:
            path = backup_scheduler.run_backup_now()
        except Exception as e:
            messagebox.showerror("Backup Failed", str(e))
            return
        show_toast(self, f"Backup saved to {path}", "success")
        self.on_show()

    def _restore(self):
        path = filedialog.askopenfilename(title="Select backup file", filetypes=[("SQLite DB", "*.db")])
        if not path:
            return
        if not messagebox.askyesno("Confirm Restore", "This will overwrite the current database. Continue?"):
            return
        try:
            backup_scheduler.restore_backup(path)
        except Exception as e:
            messagebox.showerror("Restore Failed", str(e))
            return
        messagebox.showinfo("Restored", "Database restored. Please restart the app.")

    def _save_interval(self):
        try:
            hours = float(self.interval_entry.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Value", "Interval must be a number.")
            return
        set_setting("backup_interval_hours", hours)
        show_toast(self, "Backup interval saved", "success")
