from datetime import date, datetime

import cv2

import config
from config import FRAME_SKIP, RESIZE_FACTOR
from db import queries
from ml.camera import CameraThread
from ml.detector import FaceDetector
from ml.liveness import LivenessChecker
from ml.preprocessing import enhance_low_light
from ml.recognizer import Recognizer
from services import notifications


class SessionController:
    """Owns the camera + ML pipeline for one live attendance session."""

    def __init__(self):
        self.camera = CameraThread(config.CAMERA_INDEX)
        self.detector = FaceDetector()
        self.recognizer = Recognizer()
        self.liveness = LivenessChecker()
        self.session_id = None          # "last resolved session id" — kept for QR/substitute/manual-
                                         # override UI actions that need *a* session_id to act on
        self._slot_session_cache = {}   # timetable_slot_id -> session_id, resolved today
        self._fallback_session_id = None
        self._today = None              # local date string, refreshed if the loop straddles midnight
        self._created_by_user_id = None
        self._faculty_name = None       # full_name of whoever's logged in and running this session
        self._frame_count = 0
        self._stored_encodings = []
        self.present_students = {}  # student_id -> name
        self.unknown_count = 0
        self.spoof_count = 0
        self.paused = False
        self.total_enrolled = 0
        self._last_labels = []  # parallel to last detected boxes
        self._last_boxes = []  # reused on skipped frames so the overlay doesn't flicker
        self._match_streaks = {}  # student_id -> consecutive detection ticks matched in a row

    def start(self, user_id: int = None) -> bool:
        """Starts (or resumes) today's always-on auto-attendance watching. No subject/section/
        faculty input is needed — each recognized student's session is resolved from their own
        department/year/semester against the timetable on every recognition."""
        if not self.camera.start():
            return False
        self._today = date.today().isoformat()
        self._slot_session_cache = {}
        self._fallback_session_id = None
        self.session_id = None          # no longer eagerly created; resolved per-recognition
        self._created_by_user_id = user_id
        user = queries.get_user(user_id) if user_id is not None else None
        self._faculty_name = user["full_name"] if user and user["full_name"] else None
        self._stored_encodings = queries.get_all_encodings()
        self.total_enrolled = len(queries.list_students())
        self.present_students = {}
        self.unknown_count = 0
        self._frame_count = 0
        self.spoof_count = 0
        self.paused = False
        self._last_labels = []
        self._match_streaks = {}
        self.liveness.reset_all()
        return True

    def toggle_pause(self):
        self.paused = not self.paused
        return self.paused

    def refresh_encodings(self):
        """Reloads known-face encodings from the DB. Must be called after enrolling/editing/
        deleting a student, since the camera loop otherwise keeps matching against the stale
        list it loaded at start() — newly enrolled faces would show as 'Unknown' forever."""
        self._stored_encodings = queries.get_all_encodings()
        self.total_enrolled = len(queries.list_students())

    def _resolve_session_for_student(self, student):
        """Given a recognized student row, find/create the session for their current period."""
        now = datetime.now()
        today_str = now.date().isoformat()
        if today_str != self._today:                      # midnight rollover while camera stays open
            self._today = today_str
            self._slot_session_cache = {}
            self._fallback_session_id = None
        dow = now.weekday()                                 # Monday=0, matches timetable_slots.day_of_week
        time_str = now.strftime("%H:%M")
        slot = queries.find_active_timetable_slot(
            student["department"], student["year"], student["semester"], dow, time_str,
            faculty=self._faculty_name)
        if slot is None:
            if self._fallback_session_id is None:
                self._fallback_session_id = queries.get_or_create_fallback_session(today_str, self._created_by_user_id)
            return self._fallback_session_id
        if slot["id"] not in self._slot_session_cache:
            self._slot_session_cache[slot["id"]] = queries.get_or_create_slot_session(
                slot, today_str, self._created_by_user_id)
        return self._slot_session_cache[slot["id"]]

    def _resolve_fallback_session(self):
        """Session used for faces that can't be attributed to a student (unknown/spoof)."""
        today_str = date.today().isoformat()
        if today_str != self._today:
            self._today = today_str
            self._slot_session_cache = {}
            self._fallback_session_id = None
        if self._fallback_session_id is None:
            self._fallback_session_id = queries.get_or_create_fallback_session(today_str, self._created_by_user_id)
        return self._fallback_session_id

    def process_next_frame(self):
        """Reads one frame, runs detection/recognition per FRAME_SKIP policy.
        Returns (annotated_bgr_frame, faces_found_count, newly_recognized) or (None, 0, []) if no
        frame, where newly_recognized is a list of (name, subject, section) tuples."""
        frame = self.camera.get_frame()
        if frame is None:
            return None, 0, []

        if self.paused:
            return frame, 0, []

        self._frame_count += 1
        newly_recognized = []

        # Face detection (HOG) is the expensive step and runs synchronously on the UI thread —
        # only do it (and the encoding/matching that follows) every FRAME_SKIP-th tick. On the
        # skipped ticks we just redraw the raw frame with the last known boxes/labels so the
        # video feed still looks smooth without re-running detection every ~100ms.
        if self._frame_count % FRAME_SKIP == 0:
            if config.LOW_LIGHT_ENHANCEMENT_ENABLED:
                detect_frame = enhance_low_light(frame)
            else:
                detect_frame = frame
            small_frame = cv2.resize(detect_frame, (0, 0), fx=RESIZE_FACTOR, fy=RESIZE_FACTOR)
            small_rgb = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            boxes = self.detector.detect(small_rgb)
            self._last_boxes = boxes

            if boxes:
                encodings = self.recognizer.encode_faces(small_rgb, boxes)
                labels = []
                matched_this_tick = set()
                for box, encoding in zip(boxes, encodings):
                    if config.LIVENESS_ENABLED:
                        top, right, bottom, left = box
                        face_roi = small_frame[max(top, 0):bottom, max(left, 0):right]
                        if not self.liveness.is_live(face_roi):
                            spoof_sid = self._resolve_fallback_session()
                            queries.log_spoof_attempt(spoof_sid)
                            self.session_id = spoof_sid
                            self.spoof_count += 1
                            labels.append("Spoof?")
                            continue

                    student_id, distance = self.recognizer.match(encoding, self._stored_encodings)
                    if student_id is not None:
                        matched_this_tick.add(student_id)
                        streak = self._match_streaks.get(student_id, 0) + 1
                        self._match_streaks[student_id] = streak
                        student = queries.get_student(student_id)

                        # A blink is required before marking present, since a static held-up
                        # photo/screen can pass the texture check but cannot blink — this is
                        # what actually catches the "photo on a phone" spoof.
                        if config.LIVENESS_ENABLED:
                            blinked = self.liveness.observe_blink(student_id, small_rgb, box)
                        else:
                            blinked = True

                        if streak >= config.ATTENDANCE_CONFIRM_STREAK and blinked:
                            labels.append(student["name"])
                            sid = self._resolve_session_for_student(student)
                            is_new = queries.mark_present(sid, student_id, distance)
                            self.session_id = sid
                            self.present_students[student_id] = student["name"]
                            if is_new:
                                session_row = queries.get_session(sid)
                                subject = session_row["subject"] if session_row else None
                                section = session_row["section"] if session_row else None
                                newly_recognized.append((student["name"], subject, section))
                        else:
                            labels.append(f"{student['name']} (confirming)")
                    else:
                        unknown_sid = self._resolve_fallback_session()
                        queries.log_unknown(unknown_sid, distance)
                        self.session_id = unknown_sid
                        self.unknown_count += 1
                        labels.append("Unknown")
                # Reset streaks/blink-tracking for students not seen this tick so a brief
                # mismatch doesn't carry over stale state into a later, unrelated sighting.
                for sid in list(self._match_streaks):
                    if sid not in matched_this_tick:
                        del self._match_streaks[sid]
                        self.liveness.reset_track(sid)
                self._last_labels = labels
            else:
                self._match_streaks.clear()
                self._last_labels = []

        annotated = self._annotate(frame, self._last_boxes)
        return annotated, len(self._last_boxes), newly_recognized

    def _annotate(self, frame_bgr, small_boxes):
        scale = 1.0 / RESIZE_FACTOR
        labels = self._last_labels if len(self._last_labels) == len(small_boxes) else [None] * len(small_boxes)
        for (top, right, bottom, left), label in zip(small_boxes, labels):
            t, r, b, l = int(top * scale), int(right * scale), int(bottom * scale), int(left * scale)
            if label == "Unknown":
                color = (231, 76, 60)
            elif label == "Spoof?":
                color = (155, 89, 182)
            else:
                color = (46, 204, 113)
            cv2.rectangle(frame_bgr, (l, t), (r, b), color, 2)
            if label:
                cv2.rectangle(frame_bgr, (l, b - 22), (r, b), color, cv2.FILLED)
                cv2.putText(frame_bgr, label, (l + 4, b - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        return frame_bgr

    def manual_override(self, student_id: int, status: str):
        student = queries.get_student(student_id)
        sid = self._resolve_session_for_student(student)
        queries.manual_override(sid, student_id, status)
        self.session_id = sid
        if status in ("present", "manual"):
            self.present_students[student_id] = student["name"]
        elif student_id in self.present_students:
            del self.present_students[student_id]

    def stop_watching(self):
        """Stops the camera/ML pipeline without finalizing absentees — open sessions stay open
        so watching can resume later. Use close_day() to finalize absentees for everyone."""
        self.camera.stop()
        self.detector.close()
        self.liveness.close()
        return self.session_id


def close_day():
    """Finalizes absentees and ends every session still open today (one per subject/slot +
    fallback). Returns the list of closed session ids."""
    session_ids = queries.close_day()
    for session_id in session_ids:
        if config.NOTIFY_ON_SESSION_END:
            notifications.notify_session_absentees(session_id)
    if session_ids and config.NOTIFY_DEFAULTER_CHECK:
        notifications.notify_low_attendance_students()
    return session_ids
