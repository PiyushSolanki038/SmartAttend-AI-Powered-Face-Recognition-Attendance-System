import threading
import time

import cv2

_MAX_CONSECUTIVE_FAILURES = 30
_FAILURE_RETRY_DELAY = 0.05
_RECONNECT_DELAY = 1.0


class CameraThread:
    """Background webcam capture thread. Latest frame is read via get_frame()."""

    def __init__(self, camera_index: int = 0):
        self._camera_index = camera_index
        self._cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._healthy = False

    def start(self) -> bool:
        self._cap = cv2.VideoCapture(self._camera_index)
        if not self._cap.isOpened():
            return False
        self._healthy = True
        self._running = True
        self._thread = threading.Thread(target=self._update, daemon=True)
        self._thread.start()
        return True

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    def _reconnect(self):
        if self._cap is not None:
            self._cap.release()
        self._cap = cv2.VideoCapture(self._camera_index)

    def _update(self):
        failures = 0
        while self._running:
            ok, frame = self._cap.read()
            if not ok:
                failures += 1
                with self._lock:
                    self._healthy = False
                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    self._reconnect()
                    failures = 0
                    time.sleep(_RECONNECT_DELAY)
                else:
                    time.sleep(_FAILURE_RETRY_DELAY)
                continue
            failures = 0
            with self._lock:
                self._frame = frame
                self._healthy = True

    def get_frame(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self._cap is not None:
            self._cap.release()
