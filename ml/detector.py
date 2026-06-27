import face_recognition.api as face_api

_MIN_BOX_FRACTION = 0.06  # a detected face must span at least this fraction of the frame's shorter side
_MIN_CONFIDENCE = 0.2     # dlib HOG detector score; raise this if background clutter still gets flagged as "faces"


class FaceDetector:
    """Wraps face_recognition's HOG-based face detector (dlib), but calls dlib's detector
    directly (instead of face_recognition.face_locations) so we can read each detection's
    confidence score and filter out background false-positives (HOG is prone to mistaking
    textured backgrounds/objects for faces, especially when upsampled)."""

    def __init__(self, upsample: int = 1, min_confidence: float = _MIN_CONFIDENCE):
        # Live attendance frames are shrunk by RESIZE_FACTOR before detection, so faces are
        # often small — upsampling once (default) lets HOG find them; 0 only works well on
        # full-resolution frames (e.g. enrollment photos).
        self._upsample = upsample
        self._min_confidence = min_confidence

    def detect(self, frame_rgb):
        """frame_rgb: HxWx3 RGB ndarray. Returns list of (top, right, bottom, left) boxes,
        filtered by detector confidence and a minimum size to reject background clutter."""
        height, width = frame_rgb.shape[:2]
        min_box_size = min(height, width) * _MIN_BOX_FRACTION

        rects, scores, _ = face_api.face_detector.run(frame_rgb, self._upsample, 0.0)
        boxes = []
        for rect, score in zip(rects, scores):
            if score < self._min_confidence:
                continue
            top, right, bottom, left = rect.top(), rect.right(), rect.bottom(), rect.left()
            if (bottom - top) < min_box_size or (right - left) < min_box_size:
                continue
            top, left = max(top, 0), max(left, 0)
            bottom, right = min(bottom, height), min(right, width)
            boxes.append((top, right, bottom, left))
        return boxes

    def close(self):
        pass
