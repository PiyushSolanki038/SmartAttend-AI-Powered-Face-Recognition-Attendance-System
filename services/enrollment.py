import csv
import os

import cv2

from config import MIN_ENCODINGS
from db import queries
from ml.detector import FaceDetector
from ml.recognizer import Recognizer


class EnrollmentError(Exception):
    pass


def _validate_student_fields(roll_no: str, name: str, year, semester):
    if not roll_no or not roll_no.strip():
        raise EnrollmentError("Roll number is required.")
    if not name or not name.strip():
        raise EnrollmentError("Name is required.")
    if year is not None and not (1 <= int(year) <= 8):
        raise EnrollmentError("Year must be between 1 and 8.")
    if semester is not None and not (1 <= int(semester) <= 16):
        raise EnrollmentError("Semester must be between 1 and 16.")


def _encode_frame(detector, recognizer, frame_bgr, source_label: str):
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    boxes = detector.detect(frame_rgb)
    if not boxes:
        raise EnrollmentError(f"No face detected in: {source_label}")
    face_encodings = recognizer.encode_faces(frame_rgb, boxes[:1])
    if not face_encodings:
        raise EnrollmentError(f"Could not encode face in: {source_label}")
    return face_encodings[0]


def encode_images(image_paths: list):
    """Detect + encode a face in each image. Raises EnrollmentError if any image has no face,
    or if fewer than MIN_ENCODINGS images are provided. Returns (averaged_encoding, individual_encodings)."""
    if len(image_paths) < MIN_ENCODINGS:
        raise EnrollmentError(f"At least {MIN_ENCODINGS} images are required, got {len(image_paths)}.")

    detector = FaceDetector()
    recognizer = Recognizer()
    encodings = []
    try:
        for path in image_paths:
            frame_bgr = cv2.imread(path)
            if frame_bgr is None:
                raise EnrollmentError(f"Could not read image: {path}")
            encodings.append(_encode_frame(detector, recognizer, frame_bgr, path))
    finally:
        detector.close()

    return recognizer.average_encoding(encodings), encodings


def encode_captured_frames(frames_bgr: list):
    """Same as encode_images but for in-memory frames captured live from the webcam.
    Returns (averaged_encoding, individual_encodings)."""
    if len(frames_bgr) < MIN_ENCODINGS:
        raise EnrollmentError(f"At least {MIN_ENCODINGS} captures are required, got {len(frames_bgr)}.")

    detector = FaceDetector()
    recognizer = Recognizer()
    encodings = []
    try:
        for idx, frame_bgr in enumerate(frames_bgr):
            encodings.append(_encode_frame(detector, recognizer, frame_bgr, f"capture #{idx + 1}"))
    finally:
        detector.close()

    return recognizer.average_encoding(encodings), encodings


def add_student(roll_no: str, name: str, department: str, year: int, semester: int, image_paths: list) -> int:
    _validate_student_fields(roll_no, name, year, semester)
    averaged_encoding, individual_encodings = encode_images(image_paths)
    student_id = queries.insert_student(roll_no, name, department, year, semester, averaged_encoding)
    for enc in individual_encodings:
        queries.insert_student_encoding(student_id, enc, source="enrollment")
    return student_id


def add_student_from_frames(roll_no: str, name: str, department: str, year: int, semester: int, frames_bgr: list) -> int:
    _validate_student_fields(roll_no, name, year, semester)
    averaged_encoding, individual_encodings = encode_captured_frames(frames_bgr)
    student_id = queries.insert_student(roll_no, name, department, year, semester, averaged_encoding)
    for enc in individual_encodings:
        queries.insert_student_encoding(student_id, enc, source="webcam")
    return student_id


def update_student_info(student_id: int, roll_no: str, name: str, department: str, year: int, semester: int):
    _validate_student_fields(roll_no, name, year, semester)
    queries.update_student(student_id, roll_no, name, department, year, semester)


def update_student_photos(student_id: int, image_paths: list):
    averaged_encoding, individual_encodings = encode_images(image_paths)
    queries.update_student_encoding(student_id, averaged_encoding)
    for enc in individual_encodings:
        queries.insert_student_encoding(student_id, enc, source="enrollment")


def update_student_photos_from_frames(student_id: int, frames_bgr: list):
    averaged_encoding, individual_encodings = encode_captured_frames(frames_bgr)
    queries.update_student_encoding(student_id, averaged_encoding)
    for enc in individual_encodings:
        queries.insert_student_encoding(student_id, enc, source="webcam")


def delete_student(student_id: int):
    queries.delete_student(student_id)


def list_students():
    return queries.list_students()


def bulk_import_csv(csv_path: str):
    """CSV columns: roll_no,name,department,year,semester,photo_folder
    photo_folder must contain >= MIN_ENCODINGS image files for that student.
    Returns (success_count, list_of_error_strings). Continues past per-row failures."""
    errors = []
    success_count = 0

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for row_num, row in enumerate(rows, start=2):
        roll_no = (row.get("roll_no") or "").strip()
        name = (row.get("name") or "").strip()
        department = (row.get("department") or "").strip()
        year = row.get("year") or None
        semester = row.get("semester") or None
        photo_folder = (row.get("photo_folder") or "").strip()

        if not roll_no or not name or not photo_folder:
            errors.append(f"Row {row_num}: missing roll_no/name/photo_folder")
            continue
        if not os.path.isdir(photo_folder):
            errors.append(f"Row {row_num} ({roll_no}): photo folder not found: {photo_folder}")
            continue

        image_paths = [
            os.path.join(photo_folder, fname)
            for fname in sorted(os.listdir(photo_folder))
            if fname.lower().endswith((".jpg", ".jpeg", ".png"))
        ]

        try:
            year_val = int(year) if year else None
            semester_val = int(semester) if semester else None
            add_student(roll_no, name, department, year_val, semester_val, image_paths)
            success_count += 1
        except (EnrollmentError, ValueError) as e:
            errors.append(f"Row {row_num} ({roll_no}): {e}")

    return success_count, errors
