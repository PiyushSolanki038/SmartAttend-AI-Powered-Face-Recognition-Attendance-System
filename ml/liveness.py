import cv2

import config


class LivenessChecker:
    """Lightweight, dependency-free anti-spoof check: flags flat printed-photo/screen
    spoofs via texture/sharpness scoring (Laplacian variance) on the face ROI. On a small,
    motion-blurred, or low-res ROI this score can dip on a real face too — tune the threshold
    via config.LIVENESS_TEXTURE_MIN if you see real faces flagged as "Spoof?"."""

    def texture_score(self, face_roi_bgr) -> float:
        if face_roi_bgr is None or face_roi_bgr.size == 0:
            return 0.0
        gray = cv2.cvtColor(face_roi_bgr, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def is_live(self, face_roi_bgr) -> bool:
        return self.texture_score(face_roi_bgr) >= config.LIVENESS_TEXTURE_MIN

    def close(self):
        pass
