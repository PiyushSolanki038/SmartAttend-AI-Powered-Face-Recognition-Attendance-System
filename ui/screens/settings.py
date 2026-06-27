from tkinter import messagebox

import cv2
import customtkinter as ctk

import config


class SettingsScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkButton(header, text="< Back", width=80, command=lambda: self.app.show_screen("HomeScreen")).pack(side="left")
        ctk.CTkLabel(header, text="Settings", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=20)

        form = ctk.CTkFrame(self)
        form.pack(padx=40, pady=20, fill="x")

        ctk.CTkLabel(form, text="Recognition Tolerance (lower = stricter)").grid(row=0, column=0, sticky="w", padx=10, pady=10)
        self.tolerance_slider = ctk.CTkSlider(form, from_=0.3, to=0.9, number_of_steps=60, command=self._on_tolerance_change)
        self.tolerance_slider.set(config.TOLERANCE)
        self.tolerance_slider.grid(row=0, column=1, padx=10, pady=10)
        self.tolerance_value_label = ctk.CTkLabel(form, text=f"{config.TOLERANCE:.2f}")
        self.tolerance_value_label.grid(row=0, column=2, padx=10)

        ctk.CTkLabel(form, text="Session Timeout (minutes)").grid(row=1, column=0, sticky="w", padx=10, pady=10)
        self.timeout_entry = ctk.CTkEntry(form, width=100)
        self.timeout_entry.insert(0, str(config.SESSION_TIMEOUT_MINUTES))
        self.timeout_entry.grid(row=1, column=1, padx=10, pady=10, sticky="w")

        ctk.CTkLabel(form, text="Camera Index").grid(row=2, column=0, sticky="w", padx=10, pady=10)
        self.camera_dropdown = ctk.CTkOptionMenu(form, values=[str(i) for i in self._detect_cameras()])
        self.camera_dropdown.set(str(config.CAMERA_INDEX))
        self.camera_dropdown.grid(row=2, column=1, padx=10, pady=10, sticky="w")

        ctk.CTkLabel(form, text="Theme").grid(row=3, column=0, sticky="w", padx=10, pady=10)
        self.theme_switch = ctk.CTkOptionMenu(form, values=["dark", "light"], command=self._on_theme_change)
        self.theme_switch.set(config.THEME)
        self.theme_switch.grid(row=3, column=1, padx=10, pady=10, sticky="w")

        ctk.CTkLabel(form, text="Liveness / Anti-Spoof Check").grid(row=4, column=0, sticky="w", padx=10, pady=10)
        self.liveness_switch = ctk.CTkSwitch(form, text="Block flat/printed-photo spoofs")
        if config.LIVENESS_ENABLED:
            self.liveness_switch.select()
        self.liveness_switch.grid(row=4, column=1, padx=10, pady=10, sticky="w")

        ctk.CTkLabel(form, text="Low-Light Enhancement").grid(row=5, column=0, sticky="w", padx=10, pady=10)
        self.lowlight_switch = ctk.CTkSwitch(form, text="Auto-enhance dim frames")
        if config.LOW_LIGHT_ENHANCEMENT_ENABLED:
            self.lowlight_switch.select()
        self.lowlight_switch.grid(row=5, column=1, padx=10, pady=10, sticky="w")

        notif_form = ctk.CTkFrame(self)
        notif_form.pack(padx=40, pady=(0, 10), fill="x")
        ctk.CTkLabel(notif_form, text="Notifications", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(notif_form, text="SMTP Host").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        self.smtp_host_entry = ctk.CTkEntry(notif_form, width=200)
        self.smtp_host_entry.insert(0, config.SMTP_HOST)
        self.smtp_host_entry.grid(row=1, column=1, padx=10, pady=6, sticky="w")

        ctk.CTkLabel(notif_form, text="SMTP Port").grid(row=2, column=0, sticky="w", padx=10, pady=6)
        self.smtp_port_entry = ctk.CTkEntry(notif_form, width=100)
        self.smtp_port_entry.insert(0, str(config.SMTP_PORT))
        self.smtp_port_entry.grid(row=2, column=1, padx=10, pady=6, sticky="w")

        ctk.CTkLabel(notif_form, text="SMTP User (email)").grid(row=3, column=0, sticky="w", padx=10, pady=6)
        self.smtp_user_entry = ctk.CTkEntry(notif_form, width=200)
        self.smtp_user_entry.insert(0, config.SMTP_USER)
        self.smtp_user_entry.grid(row=3, column=1, padx=10, pady=6, sticky="w")

        ctk.CTkLabel(notif_form, text="SMTP Password").grid(row=4, column=0, sticky="w", padx=10, pady=6)
        self.smtp_password_entry = ctk.CTkEntry(notif_form, width=200, show="*")
        self.smtp_password_entry.grid(row=4, column=1, padx=10, pady=6, sticky="w")
        ctk.CTkLabel(notif_form, text="(not saved to disk — re-enter each session)", font=ctk.CTkFont(size=10), text_color="#AAAAAA").grid(row=5, column=0, columnspan=2, sticky="w", padx=10)

        self.notify_session_switch = ctk.CTkSwitch(notif_form, text="Notify on session end (absentees)")
        if config.NOTIFY_ON_SESSION_END:
            self.notify_session_switch.select()
        self.notify_session_switch.grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=6)

        self.notify_defaulter_switch = ctk.CTkSwitch(notif_form, text="Notify when viewing defaulters")
        if config.NOTIFY_DEFAULTER_CHECK:
            self.notify_defaulter_switch.select()
        self.notify_defaulter_switch.grid(row=7, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 10))

        ctk.CTkButton(self, text="Save Settings", command=self._save).pack(pady=20)

    def _detect_cameras(self, max_check=4):
        available = []
        for i in range(max_check):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                available.append(i)
            cap.release()
        return available or [0]

    def _on_tolerance_change(self, value):
        self.tolerance_value_label.configure(text=f"{value:.2f}")

    def _on_theme_change(self, value):
        ctk.set_appearance_mode(value)

    def _save(self):
        try:
            timeout = int(self.timeout_entry.get().strip())
            if timeout <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Value", "Session Timeout must be a positive whole number.")
            return

        config.TOLERANCE = round(self.tolerance_slider.get(), 2)
        config.CAMERA_INDEX = int(self.camera_dropdown.get())
        config.THEME = self.theme_switch.get()
        config.SESSION_TIMEOUT_MINUTES = timeout
        config.LIVENESS_ENABLED = bool(self.liveness_switch.get())
        config.LOW_LIGHT_ENHANCEMENT_ENABLED = bool(self.lowlight_switch.get())
        config.SMTP_HOST = self.smtp_host_entry.get().strip()
        try:
            config.SMTP_PORT = int(self.smtp_port_entry.get().strip() or 587)
        except ValueError:
            config.SMTP_PORT = 587
        config.SMTP_USER = self.smtp_user_entry.get().strip()
        password = self.smtp_password_entry.get()
        if password:
            config.SMTP_PASSWORD = password  # in-memory only, never persisted
        config.NOTIFY_ON_SESSION_END = bool(self.notify_session_switch.get())
        config.NOTIFY_DEFAULTER_CHECK = bool(self.notify_defaulter_switch.get())
        config.save_settings()
        messagebox.showinfo("Saved", "Settings saved and will persist across restarts.")
