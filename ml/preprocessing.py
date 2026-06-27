import cv2


def enhance_low_light(frame_bgr, brightness_threshold: float = 70.0):
    """Applies CLAHE on the L-channel (LAB color space) when the frame is dim.
    Cheap, no new dependency — pure OpenCV. Returns the original frame untouched if bright enough."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    if gray.mean() >= brightness_threshold:
        return frame_bgr
    lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    enhanced = cv2.merge((l, a, b))
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
