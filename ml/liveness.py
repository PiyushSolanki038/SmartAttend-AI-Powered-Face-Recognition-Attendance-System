import math

import cv2
import face_recognition
import numpy as np

import config


def _eye_aspect_ratio(eye_points) -> float:
    """Standard EAR formula (Soukupova & Cech): vertical eye openness over horizontal eye
    width, using the 6-point eye landmark face_recognition returns. Open eye ~0.25-0.35,
    closed eye (blink) drops sharply towards 0."""
    p = [np.array(pt, dtype=np.float64) for pt in eye_points]
    vertical_1 = math.dist(p[1], p[5])
    vertical_2 = math.dist(p[2], p[4])
    horizontal = math.dist(p[0], p[3])
    if horizontal == 0:
        return 0.0
    return (vertical_1 + vertical_2) / (2.0 * horizontal)


class LivenessChecker:
    """Anti-spoof check with two complementary signals:

    1. Texture/sharpness (Laplacian variance) — catches flat, blurry printed-photo spoofs.
    2. Blink detection (Eye Aspect Ratio dip) — catches a photo or video held up to the camera,
       which (1) alone misses since a sharp on-screen photo can score just as "textured" as a
       real face. A static photo physically cannot blink, so session.py requires a detected
       blink within the attendance confirm window (see config.ATTENDANCE_CONFIRM_STREAK) before
       marking someone present, in addition to passing the texture check on every frame.

    EAR state is tracked per matched face across calls via track_id (the session loop passes the
    matched student_id), since a blink only shows up as a dip-then-recovery across frames, not in
    a single frame."""

    def __init__(self):
        self._ear_history = {}  # track_id -> list of recent EAR values
        self._blink_confirmed = set()  # track_ids that have blinked at least once

    def texture_score(self, face_roi_bgr) -> float:
        if face_roi_bgr is None or face_roi_bgr.size == 0:
            return 0.0
        gray = cv2.cvtColor(face_roi_bgr, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def observe_blink(self, track_id, frame_rgb, face_box) -> bool:
        """Feeds one frame's landmarks for a tracked face into its EAR history and returns
        whether a blink has been confirmed for this track_id (sticky once True)."""
        landmarks_list = face_recognition.face_landmarks(frame_rgb, [face_box])
        if not landmarks_list:
            return track_id in self._blink_confirmed
        landmarks = landmarks_list[0]
        if "left_eye" not in landmarks or "right_eye" not in landmarks:
            return track_id in self._blink_confirmed

        ear = (_eye_aspect_ratio(landmarks["left_eye"]) + _eye_aspect_ratio(landmarks["right_eye"])) / 2.0
        history = self._ear_history.setdefault(track_id, [])
        history.append(ear)
        if len(history) > config.LIVENESS_BLINK_WINDOW:
            history.pop(0)

        if len(history) >= 3:
            open_before = max(history[:-1])
            if open_before >= config.LIVENESS_EAR_OPEN_MIN and ear <= config.LIVENESS_EAR_CLOSED_MAX:
                self._blink_confirmed.add(track_id)

        return track_id in self._blink_confirmed

    def reset_track(self, track_id):
        self._ear_history.pop(track_id, None)
        self._blink_confirmed.discard(track_id)

    def reset_all(self):
        self._ear_history.clear()
        self._blink_confirmed.clear()

    def is_live(self, face_roi_bgr) -> bool:
        return self.texture_score(face_roi_bgr) >= config.LIVENESS_TEXTURE_MIN

    def close(self):
        pass
