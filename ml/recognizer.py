import face_recognition
import numpy as np

from config import TOLERANCE


class Recognizer:
    """Encodes faces and matches them against stored student encodings."""

    def encode_faces(self, frame_rgb, face_boxes):
        """face_boxes: list of (top, right, bottom, left). Returns list of 128-d encodings (same order)."""
        if not face_boxes:
            return []
        return face_recognition.face_encodings(frame_rgb, known_face_locations=face_boxes)

    def average_encoding(self, encodings: list) -> np.ndarray:
        return np.mean(np.array(encodings), axis=0)

    def match(self, face_encoding, stored_encodings):
        """stored_encodings: list of (student_id, encoding). Returns (student_id, distance) or (None, None)."""
        if not stored_encodings:
            return None, None
        ids = [s_id for s_id, _ in stored_encodings]
        vectors = [enc for _, enc in stored_encodings]
        distances = face_recognition.face_distance(vectors, face_encoding)
        best_idx = int(np.argmin(distances))
        best_distance = float(distances[best_idx])
        if best_distance < TOLERANCE:
            return ids[best_idx], best_distance
        return None, best_distance
