from tkinter import filedialog, messagebox

import customtkinter as ctk

from db import queries
from services import audit
from services import timetable as timetable_service
from ui.components.student_table import StudentTable
from ui.components.toast import show_toast

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class TimetableScreen(ctk.CTkFrame):
    """Lets faculty/admin define the weekly class schedule per cohort (department/year/
    semester), which the student portal's Timetable page reads to show upcoming sessions.

    Supports add/edit/delete of individual slots, CSV bulk import/export, day-of-week +
    text search filtering of the list, and a same-faculty double-booking conflict check."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._editing_slot_id = None

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkButton(header, text="< Back", width=80, command=lambda: self.app.show_screen("HomeScreen")).pack(side="left")
        ctk.CTkLabel(header, text="Timetable", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=20)
        ctk.CTkButton(header, text="Refresh", width=90, command=self._refresh).pack(side="right")

        # ---------- Add/Edit form ----------
        form = ctk.CTkFrame(self)
        form.pack(padx=20, pady=10, fill="x")

        self.form_title = ctk.CTkLabel(form, text="Add Slot", font=ctk.CTkFont(weight="bold"))
        self.form_title.grid(row=0, column=0, columnspan=6, padx=6, pady=(8, 0), sticky="w")

        ctk.CTkLabel(form, text="Department").grid(row=1, column=0, padx=6, pady=8, sticky="e")
        self.dept_entry = ctk.CTkEntry(form, width=100)
        self.dept_entry.grid(row=1, column=1, padx=6, pady=8)

        ctk.CTkLabel(form, text="Year").grid(row=1, column=2, padx=6, pady=8, sticky="e")
        self.year_entry = ctk.CTkEntry(form, width=60)
        self.year_entry.grid(row=1, column=3, padx=6, pady=8)

        ctk.CTkLabel(form, text="Semester").grid(row=1, column=4, padx=6, pady=8, sticky="e")
        self.sem_entry = ctk.CTkEntry(form, width=60)
        self.sem_entry.grid(row=1, column=5, padx=6, pady=8)

        ctk.CTkLabel(form, text="Subject").grid(row=2, column=0, padx=6, pady=8, sticky="e")
        self.subject_entry = ctk.CTkEntry(form, width=140)
        self.subject_entry.grid(row=2, column=1, padx=6, pady=8)

        ctk.CTkLabel(form, text="Section").grid(row=2, column=2, padx=6, pady=8, sticky="e")
        self.section_entry = ctk.CTkEntry(form, width=80)
        self.section_entry.grid(row=2, column=3, padx=6, pady=8)

        ctk.CTkLabel(form, text="Faculty").grid(row=2, column=4, padx=6, pady=8, sticky="e")
        self.faculty_entry = ctk.CTkEntry(form, width=120)
        self.faculty_entry.grid(row=2, column=5, padx=6, pady=8)

        ctk.CTkLabel(form, text="Day").grid(row=3, column=0, padx=6, pady=8, sticky="e")
        self.day_dropdown = ctk.CTkOptionMenu(form, values=DAYS)
        self.day_dropdown.grid(row=3, column=1, padx=6, pady=8, sticky="w")

        ctk.CTkLabel(form, text="Start (HH:MM)").grid(row=3, column=2, padx=6, pady=8, sticky="e")
        self.start_entry = ctk.CTkEntry(form, width=80, placeholder_text="09:00")
        self.start_entry.grid(row=3, column=3, padx=6, pady=8)

        ctk.CTkLabel(form, text="End (HH:MM)").grid(row=3, column=4, padx=6, pady=8, sticky="e")
        self.end_entry = ctk.CTkEntry(form, width=80, placeholder_text="10:00")
        self.end_entry.grid(row=3, column=5, padx=6, pady=8)

        button_row = ctk.CTkFrame(form, fg_color="transparent")
        button_row.grid(row=4, column=0, columnspan=6, pady=10)
        self.save_btn = ctk.CTkButton(button_row, text="Add Slot", command=self._save_slot)
        self.save_btn.pack(side="left", padx=5)
        self.cancel_edit_btn = ctk.CTkButton(
            button_row, text="Cancel Edit", fg_color="#6B7280", hover_color="#4B5563",
            command=self._cancel_edit,
        )
        ctk.CTkButton(button_row, text="Import CSV", fg_color="#2E86DE", hover_color="#2874A6",
                      command=self._bulk_import).pack(side="left", padx=5)
        ctk.CTkButton(button_row, text="Export CSV", fg_color="#2E86DE", hover_color="#2874A6",
                      command=self._export_csv).pack(side="left", padx=5)

        # ---------- Filter bar ----------
        filter_bar = ctk.CTkFrame(self, fg_color="transparent")
        filter_bar.pack(fill="x", padx=20, pady=(0, 5))
        ctk.CTkLabel(filter_bar, text="Day filter").pack(side="left", padx=(0, 5))
        self.day_filter = ctk.CTkOptionMenu(filter_bar, values=["All"] + DAYS, width=120, command=lambda _: self._render_table())
        self.day_filter.pack(side="left", padx=5)
        ctk.CTkLabel(filter_bar, text="Search").pack(side="left", padx=(15, 5))
        self.search_entry = ctk.CTkEntry(filter_bar, width=220, placeholder_text="Subject or faculty...")
        self.search_entry.pack(side="left", padx=5)
        self.search_entry.bind("<KeyRelease>", lambda e: self._render_table())
        self.count_label = ctk.CTkLabel(filter_bar, text="", text_color="gray")
        self.count_label.pack(side="right", padx=5)

        # ---------- Table ----------
        self.table = StudentTable(
            self, headers=["ID", "Dept", "Year", "Sem", "Subject", "Section", "Faculty", "Day", "Start", "End"],
            on_row_click=self._on_row_click, height=260,
        )
        self.table.pack(fill="both", expand=True, padx=20, pady=10)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(0, 20))
        self.selected_label = ctk.CTkLabel(actions, text="No slot selected")
        self.selected_label.pack(side="left")
        ctk.CTkButton(actions, text="Edit Selected", fg_color="#F39C12", hover_color="#D68910",
                      command=self._load_selected_for_edit).pack(side="right", padx=5)
        ctk.CTkButton(actions, text="Delete Slot", fg_color="#E74C3C", hover_color="#C0392B",
                      command=self._delete_slot).pack(side="right", padx=5)

        self._slots = []
        self._visible_slots = []
        self._selected_slot_id = None

    def on_show(self):
        self._refresh()

    def _refresh(self):
        self._slots = queries.list_all_timetable_slots()
        self._render_table()

    def _render_table(self):
        day_choice = self.day_filter.get()
        search_term = self.search_entry.get().strip().lower()

        visible = self._slots
        if day_choice != "All":
            day_idx = DAYS.index(day_choice)
            visible = [s for s in visible if s["day_of_week"] == day_idx]
        if search_term:
            visible = [
                s for s in visible
                if search_term in (s["subject"] or "").lower() or search_term in (s["faculty"] or "").lower()
            ]
        self._visible_slots = visible

        self.table.set_rows([
            (s["id"], s["department"] or "--", s["year"] or "--", s["semester"] or "--",
             s["subject"], s["section"] or "--", s["faculty"] or "--",
             DAYS[s["day_of_week"]], s["start_time"], s["end_time"])
            for s in visible
        ])
        self.count_label.configure(text=f"{len(visible)} of {len(self._slots)} slot(s)")

    def _on_row_click(self, idx):
        slot = self._visible_slots[idx]
        self._selected_slot_id = slot["id"]
        self.selected_label.configure(text=f"Selected: {slot['subject']} ({DAYS[slot['day_of_week']]})")

    def _clear_form(self):
        self.dept_entry.delete(0, "end")
        self.year_entry.delete(0, "end")
        self.sem_entry.delete(0, "end")
        self.subject_entry.delete(0, "end")
        self.section_entry.delete(0, "end")
        self.faculty_entry.delete(0, "end")
        self.start_entry.delete(0, "end")
        self.end_entry.delete(0, "end")
        self.day_dropdown.set(DAYS[0])

    def _read_form(self):
        subject = self.subject_entry.get().strip()
        start_time = self.start_entry.get().strip()
        end_time = self.end_entry.get().strip()
        if not subject or not start_time or not end_time:
            messagebox.showerror("Missing Field", "Subject, start time, and end time are required.")
            return None
        return dict(
            department=self.dept_entry.get().strip() or None,
            year=int(self.year_entry.get()) if self.year_entry.get().strip().isdigit() else None,
            semester=int(self.sem_entry.get()) if self.sem_entry.get().strip().isdigit() else None,
            subject=subject,
            section=self.section_entry.get().strip() or None,
            faculty=self.faculty_entry.get().strip() or None,
            day_of_week=DAYS.index(self.day_dropdown.get()),
            start_time=start_time,
            end_time=end_time,
        )

    def _save_slot(self):
        data = self._read_form()
        if data is None:
            return

        conflicts = timetable_service.find_conflicts(
            data["faculty"], data["day_of_week"], data["start_time"], data["end_time"],
            exclude_id=self._editing_slot_id,
        )
        if conflicts:
            c = conflicts[0]
            proceed = messagebox.askyesno(
                "Scheduling Conflict",
                f"{data['faculty']} is already booked for '{c['subject']}' on {DAYS[c['day_of_week']]} "
                f"{c['start_time']}-{c['end_time']}.\n\nSave anyway?",
            )
            if not proceed:
                return

        actor_id = self.app.current_user["id"] if self.app.current_user else None
        if self._editing_slot_id is not None:
            queries.update_timetable_slot(self._editing_slot_id, **data)
            audit.log_action(actor_id, "timetable_slot_updated", "timetable_slot", self._editing_slot_id,
                              details=data["subject"])
            show_toast(self, "Timetable slot updated", "success")
            self._cancel_edit()
        else:
            new_id = queries.insert_timetable_slot(**data)
            audit.log_action(actor_id, "timetable_slot_created", "timetable_slot", new_id, details=data["subject"])
            show_toast(self, "Timetable slot added", "success")
            self._clear_form()
        self._refresh()

    def _load_selected_for_edit(self):
        if self._selected_slot_id is None:
            show_toast(self, "Select a slot first", "warning")
            return
        slot = queries.get_timetable_slot(self._selected_slot_id)
        if slot is None:
            return
        self._editing_slot_id = slot["id"]
        self._clear_form()
        self.dept_entry.insert(0, slot["department"] or "")
        self.year_entry.insert(0, str(slot["year"]) if slot["year"] else "")
        self.sem_entry.insert(0, str(slot["semester"]) if slot["semester"] else "")
        self.subject_entry.insert(0, slot["subject"])
        self.section_entry.insert(0, slot["section"] or "")
        self.faculty_entry.insert(0, slot["faculty"] or "")
        self.day_dropdown.set(DAYS[slot["day_of_week"]])
        self.start_entry.insert(0, slot["start_time"])
        self.end_entry.insert(0, slot["end_time"])

        self.form_title.configure(text=f"Editing: {slot['subject']} ({DAYS[slot['day_of_week']]})")
        self.save_btn.configure(text="Update Slot")
        self.cancel_edit_btn.pack(side="left", padx=5)

    def _cancel_edit(self):
        self._editing_slot_id = None
        self._clear_form()
        self.form_title.configure(text="Add Slot")
        self.save_btn.configure(text="Add Slot")
        self.cancel_edit_btn.pack_forget()

    def _bulk_import(self):
        csv_path = filedialog.askopenfilename(title="Select CSV", filetypes=[("CSV files", "*.csv")])
        if not csv_path:
            return
        try:
            success_count, errors = timetable_service.bulk_import_csv(csv_path)
        except Exception as e:
            messagebox.showerror("Import Failed", str(e))
            return
        self._refresh()
        message = f"Imported {success_count} timetable slot(s)."
        if errors:
            message += f"\n\n{len(errors)} error(s):\n" + "\n".join(errors[:10])
        messagebox.showinfo("Bulk Import Result", message)

    def _export_csv(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not filepath:
            return
        try:
            count = timetable_service.export_csv(filepath)
            show_toast(self, f"Exported {count} slot(s) to {filepath}", "success")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def _delete_slot(self):
        if self._selected_slot_id is None:
            show_toast(self, "Select a slot first", "warning")
            return
        if not messagebox.askyesno("Confirm Delete", "Delete this timetable slot?"):
            return
        if self._editing_slot_id == self._selected_slot_id:
            self._cancel_edit()
        actor_id = self.app.current_user["id"] if self.app.current_user else None
        audit.log_action(actor_id, "timetable_slot_deleted", "timetable_slot", self._selected_slot_id)
        queries.delete_timetable_slot(self._selected_slot_id)
        self._selected_slot_id = None
        self.selected_label.configure(text="No slot selected")
        self._refresh()
