from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

import config
from config import MIN_ENCODINGS
from db import queries
from ml.camera import CameraThread
from ml.detector import FaceDetector
from services import enrollment
from ui.components.student_table import StudentTable
from ui.components.toast import show_toast

AUTO_CAPTURE_TARGET = 5
AUTO_CAPTURE_INTERVAL_MS = 700  # minimum gap between auto-captured frames, so the 5 shots vary slightly

# Seed options for the Department combo box — it's still editable (CTkComboBox, not a fixed
# CTkOptionMenu) since a college's actual department names aren't hardcoded anywhere in this
# codebase; whatever's already in the DB is merged in on top of these so the list grows with use.
DEFAULT_DEPARTMENTS = ["CE", "IT", "CSE", "ECE", "EE", "ME", "Civil"]
YEAR_OPTIONS = ["1", "2", "3", "4"]
SEMESTER_OPTIONS = [str(n) for n in range(1, 9)]


class EnrollScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._image_paths = []
        self._captured_frames = []
        self._editing_student_id = None
        self._capture_camera = None
        self._capture_poll_job = None
        self._capture_detector = None
        self._camera_released_for_capture = False

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkButton(header, text="< Back", width=80, command=self._go_back).pack(side="left")
        ctk.CTkLabel(header, text="Enroll Student", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=20)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=10)

        form = ctk.CTkFrame(body)
        form.pack(side="left", fill="y", padx=(0, 20))

        self.roll_entry = self._labeled_entry(form, "Roll Number")
        self.name_entry = self._labeled_entry(form, "Name")
        self.dept_entry = self._labeled_combo(form, "Department", self._department_options())
        self.year_entry = self._labeled_dropdown(form, "Year", YEAR_OPTIONS)
        self.semester_entry = self._labeled_dropdown(form, "Semester", SEMESTER_OPTIONS)

        self.photo_count_label = ctk.CTkLabel(form, text="Photos selected: 0")
        self.photo_count_label.pack(pady=(10, 5), anchor="w")

        photo_btns = ctk.CTkFrame(form, fg_color="transparent")
        photo_btns.pack(fill="x")
        ctk.CTkButton(photo_btns, text="Scan Face", width=100, command=self._open_capture_dialog).pack(side="left", padx=(0, 5))
        ctk.CTkButton(photo_btns, text="From Files", width=100, fg_color="gray30", command=self._select_photos).pack(side="left")

        self.thumbnail_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.thumbnail_frame.pack(fill="x", pady=10)

        self.submit_btn = ctk.CTkButton(form, text="Add Student", command=self._submit)
        self.submit_btn.pack(pady=(20, 5), fill="x")
        ctk.CTkButton(form, text="Clear Form", fg_color="gray30", command=self._clear_form).pack(pady=5, fill="x")
        ctk.CTkButton(form, text="Bulk Import (CSV)", fg_color="gray30", command=self._bulk_import).pack(pady=5, fill="x")

        list_frame = ctk.CTkFrame(body)
        list_frame.pack(side="left", fill="both", expand=True)

        list_header = ctk.CTkFrame(list_frame, fg_color="transparent")
        list_header.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(list_header, text="Enrolled Students", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.search_entry = ctk.CTkEntry(list_header, placeholder_text="Search roll no / name...", width=220)
        self.search_entry.pack(side="right")
        self.search_entry.bind("<KeyRelease>", lambda e: self._refresh_table())

        self.table = StudentTable(list_frame, headers=["Roll No", "Name", "Department", "Attendance %", "Edit", "Delete"])
        self.table.pack(fill="both", expand=True, padx=10, pady=10)

    def _go_back(self):
        self._stop_capture()
        self.app.show_screen("HomeScreen")

    def _labeled_entry(self, parent, label_text):
        ctk.CTkLabel(parent, text=label_text).pack(anchor="w", padx=5)
        entry = ctk.CTkEntry(parent, width=220)
        entry.pack(pady=(0, 8), padx=5)
        return entry

    def _labeled_dropdown(self, parent, label_text, values):
        ctk.CTkLabel(parent, text=label_text).pack(anchor="w", padx=5)
        dropdown = ctk.CTkOptionMenu(parent, values=values, width=220)
        dropdown.set("")
        dropdown.pack(pady=(0, 8), padx=5)
        return dropdown

    def _labeled_combo(self, parent, label_text, values):
        """Like _labeled_dropdown, but editable (CTkComboBox) — department names aren't a
        fixed enum, so this offers the common/known ones without blocking a new one."""
        ctk.CTkLabel(parent, text=label_text).pack(anchor="w", padx=5)
        combo = ctk.CTkComboBox(parent, values=values, width=220)
        combo.set("")
        combo.pack(pady=(0, 8), padx=5)
        return combo

    def _department_options(self):
        known = [d for d in queries.get_distinct_departments() if d]
        merged = list(dict.fromkeys(DEFAULT_DEPARTMENTS + known))  # de-duped, order preserved
        return merged

    # ---------- Photo selection (file picker) ----------

    def _select_photos(self):
        paths = filedialog.askopenfilenames(title="Select face photos", filetypes=[("Images", "*.jpg *.jpeg *.png")])
        if paths:
            self._image_paths = list(paths)
            self._captured_frames = []
            self.photo_count_label.configure(text=f"Photos selected: {len(self._image_paths)}")
            self._render_thumbnails(self._image_paths)

    def _render_thumbnails(self, image_paths):
        for widget in self.thumbnail_frame.winfo_children():
            widget.destroy()
        for path in image_paths[:5]:
            try:
                img = Image.open(path)
                img.thumbnail((60, 60))
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                ctk.CTkLabel(self.thumbnail_frame, image=ctk_img, text="").pack(side="left", padx=2)
            except Exception:
                continue

    # ---------- Live webcam capture ----------

    def _open_capture_dialog(self):
        # Live Attendance holds the webcam continuously in the background — release it first
        # so this dialog doesn't fight over the same physical camera device.
        self.app.release_camera_for_other_use()
        self._camera_released_for_capture = True

        self._capture_camera = CameraThread(config.CAMERA_INDEX)
        if not self._capture_camera.start():
            messagebox.showerror("Camera Error", "No webcam detected.")
            self._capture_camera = None
            self.app.reclaim_camera()
            return

        self._capture_detector = FaceDetector()
        self._last_auto_capture_time = 0

        self._capture_dialog = ctk.CTkToplevel(self)
        self._capture_dialog.title("Scan Face")
        self._capture_dialog.geometry("520x580")
        self._capture_dialog.protocol("WM_DELETE_WINDOW", self._close_capture_dialog)

        self._capture_preview = ctk.CTkLabel(self._capture_dialog, text="", width=480, height=400)
        self._capture_preview.pack(padx=10, pady=10)

        self._capture_status_label = ctk.CTkLabel(self._capture_dialog, text="Look at the camera — scanning automatically...",
                                                    font=ctk.CTkFont(weight="bold"))
        self._capture_status_label.pack(pady=(0, 2))
        self._capture_count_label = ctk.CTkLabel(self._capture_dialog, text=f"Captured: 0 / {AUTO_CAPTURE_TARGET}")
        self._capture_count_label.pack(pady=5)

        btn_row = ctk.CTkFrame(self._capture_dialog, fg_color="transparent")
        btn_row.pack(pady=10)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="#E74C3C", command=self._close_capture_dialog).pack(side="left", padx=5)

        self._captured_frames = []
        self._capture_tick = 0
        self._last_capture_boxes = []
        self._poll_capture_preview()

    def _poll_capture_preview(self):
        if self._capture_camera is None:
            return
        import cv2
        import time

        self._capture_tick = getattr(self, "_capture_tick", 0) + 1
        frame = self._capture_camera.get_frame()
        if frame is not None:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Detection (HOG) is the expensive step — only run it every other tick (~200ms)
            # rather than on every preview frame, to keep the dialog responsive.
            if self._capture_tick % 2 == 0:
                self._last_capture_boxes = self._capture_detector.detect(frame_rgb)
            boxes = getattr(self, "_last_capture_boxes", [])

            if boxes:
                now = time.monotonic() * 1000
                if (now - self._last_auto_capture_time) >= AUTO_CAPTURE_INTERVAL_MS:
                    self._captured_frames.append(frame.copy())
                    self._last_auto_capture_time = now
                    self._capture_count_label.configure(text=f"Captured: {len(self._captured_frames)} / {AUTO_CAPTURE_TARGET}")
                self._capture_status_label.configure(text="Hold still — capturing...")
                for (top, right, bottom, left) in boxes:
                    cv2.rectangle(frame, (left, top), (right, bottom), (46, 204, 113), 2)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                self._capture_status_label.configure(text="No face detected — move closer / improve lighting")

            img = Image.fromarray(frame_rgb)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(480, 400))
            self._capture_preview.configure(image=ctk_img)
            self._capture_preview.image = ctk_img

            if len(self._captured_frames) >= AUTO_CAPTURE_TARGET:
                self._capture_status_label.configure(text="Scan complete!")
                self._finish_capture()
                return

        self._capture_poll_job = self._capture_dialog.after(100, self._poll_capture_preview)

    def _finish_capture(self):
        self._image_paths = []
        self.photo_count_label.configure(text=f"Photos captured: {len(self._captured_frames)} (face scan)")
        self._render_captured_thumbnails()
        self._close_capture_dialog()

    def _render_captured_thumbnails(self):
        import cv2
        for widget in self.thumbnail_frame.winfo_children():
            widget.destroy()
        for frame in self._captured_frames[:5]:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            img.thumbnail((60, 60))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            ctk.CTkLabel(self.thumbnail_frame, image=ctk_img, text="").pack(side="left", padx=2)

    def _close_capture_dialog(self):
        self._stop_capture()
        if hasattr(self, "_capture_dialog") and self._capture_dialog.winfo_exists():
            self._capture_dialog.destroy()

    def _stop_capture(self):
        if self._capture_poll_job is not None and hasattr(self, "_capture_dialog"):
            try:
                self._capture_dialog.after_cancel(self._capture_poll_job)
            except Exception:
                pass
            self._capture_poll_job = None
        if self._capture_camera is not None:
            self._capture_camera.stop()
            self._capture_camera = None
        if getattr(self, "_capture_detector", None) is not None:
            self._capture_detector.close()
            self._capture_detector = None
        if getattr(self, "_camera_released_for_capture", False):
            self._camera_released_for_capture = False
            self.app.reclaim_camera()

    # ---------- Submit / CRUD ----------

    def _submit(self):
        roll_no = self.roll_entry.get().strip()
        name = self.name_entry.get().strip()
        department = self.dept_entry.get().strip()
        year = self.year_entry.get().strip()
        semester = self.semester_entry.get().strip()

        if not roll_no or not name:
            messagebox.showerror("Missing Fields", "Roll Number and Name are required.")
            return

        try:
            year_val = int(year) if year else None
            semester_val = int(semester) if semester else None
        except ValueError:
            messagebox.showerror("Invalid Input", "Year and Semester must be numbers.")
            return

        try:
            if self._editing_student_id is not None:
                enrollment.update_student_info(self._editing_student_id, roll_no, name, department, year_val, semester_val)
                if self._captured_frames:
                    enrollment.update_student_photos_from_frames(self._editing_student_id, self._captured_frames)
                elif self._image_paths:
                    enrollment.update_student_photos(self._editing_student_id, self._image_paths)
                show_toast(self, f"{name} updated successfully", "success")
            else:
                if self._captured_frames:
                    enrollment.add_student_from_frames(roll_no, name, department, year_val, semester_val, self._captured_frames)
                elif self._image_paths:
                    enrollment.add_student(roll_no, name, department, year_val, semester_val, self._image_paths)
                else:
                    messagebox.showerror("Missing Photos", "Please select or capture 3-5 face photos.")
                    return
                show_toast(self, f"{name} enrolled successfully", "success")
        except enrollment.EnrollmentError as e:
            messagebox.showerror("Enrollment Failed", str(e))
            return
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        self.app.refresh_known_faces()
        self._clear_form()
        self._refresh_table()

    def _clear_form(self):
        self._editing_student_id = None
        self._image_paths = []
        self._captured_frames = []
        self.photo_count_label.configure(text="Photos selected: 0")
        for widget in self.thumbnail_frame.winfo_children():
            widget.destroy()
        for entry in (self.roll_entry, self.name_entry):
            entry.delete(0, "end")
        self.dept_entry.set("")
        self.year_entry.set("")
        self.semester_entry.set("")
        self.submit_btn.configure(text="Add Student")

    def _edit_student(self, student_id, roll_no, name, department, year=None, semester=None):
        self._editing_student_id = student_id
        self._image_paths = []
        self._captured_frames = []
        self.photo_count_label.configure(text="Photos selected: 0 (leave empty to keep existing)")
        for widget in self.thumbnail_frame.winfo_children():
            widget.destroy()
        self.roll_entry.delete(0, "end")
        self.roll_entry.insert(0, roll_no)
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, name)
        self.dept_entry.configure(values=self._department_options())
        self.dept_entry.set(department or "")
        self.year_entry.set(str(year) if year else "")
        self.semester_entry.set(str(semester) if semester else "")
        self.submit_btn.configure(text="Save Changes")

    def _delete_student(self, student_id, name):
        if messagebox.askyesno("Confirm Delete", f"Delete {name}? This cannot be undone."):
            enrollment.delete_student(student_id)
            self.app.refresh_known_faces()
            self._refresh_table()

    def _bulk_import(self):
        csv_path = filedialog.askopenfilename(title="Select CSV", filetypes=[("CSV files", "*.csv")])
        if not csv_path:
            return
        try:
            success_count, errors = enrollment.bulk_import_csv(csv_path)
        except Exception as e:
            messagebox.showerror("Import Failed", str(e))
            return
        self.app.refresh_known_faces()
        self._refresh_table()
        message = f"Imported {success_count} student(s)."
        if errors:
            message += f"\n\n{len(errors)} error(s):\n" + "\n".join(errors[:10])
        messagebox.showinfo("Bulk Import Result", message)

    def _refresh_table(self):
        search_term = self.search_entry.get().strip().lower()
        students = enrollment.list_students()
        if search_term:
            students = [s for s in students if search_term in s["roll_no"].lower() or search_term in s["name"].lower()]

        attendance_lookup = {row["id"]: row["percentage"] for row in queries.get_attendance_percentages()}

        for widget in self.table._row_widgets:
            widget.destroy()
        self.table._row_widgets = []

        for row_idx, s in enumerate(students, start=1):
            pct = attendance_lookup.get(s["id"], 0.0)
            roll_label = ctk.CTkLabel(self.table, text=s["roll_no"])
            roll_label.grid(row=row_idx, column=0, padx=8, pady=2, sticky="w")
            name_label = ctk.CTkLabel(self.table, text=s["name"])
            name_label.grid(row=row_idx, column=1, padx=8, pady=2, sticky="w")
            dept_label = ctk.CTkLabel(self.table, text=s["department"] or "")
            dept_label.grid(row=row_idx, column=2, padx=8, pady=2, sticky="w")
            pct_label = ctk.CTkLabel(self.table, text=f"{pct:.0f}%")
            pct_label.grid(row=row_idx, column=3, padx=8, pady=2, sticky="w")
            edit_btn = ctk.CTkButton(
                self.table, text="Edit", width=60,
                command=lambda sid=s["id"], r=s["roll_no"], n=s["name"], d=s["department"], y=s["year"], sem=s["semester"]:
                    self._edit_student(sid, r, n, d, y, sem),
            )
            edit_btn.grid(row=row_idx, column=4, padx=4, pady=2)
            delete_btn = ctk.CTkButton(
                self.table, text="Delete", width=60, fg_color="#E74C3C", hover_color="#C0392B",
                command=lambda sid=s["id"], n=s["name"]: self._delete_student(sid, n),
            )
            delete_btn.grid(row=row_idx, column=5, padx=4, pady=2)
            self.table._row_widgets.extend([roll_label, name_label, dept_label, pct_label, edit_btn, delete_btn])

    def on_show(self):
        self.dept_entry.configure(values=self._department_options())
        self._refresh_table()

    def on_close(self):
        self._stop_capture()
