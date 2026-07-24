import os
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

import cv2
import time


class Camera:
    def __init__(self, rtsp_url):
        self.rtsp_url = rtsp_url
        self.cap = None

    def connect(self):
        if self.cap is not None:
            self.cap.release()

        self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)

        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.cap.isOpened():
            raise Exception("Unable to open camera stream")

        print("[CAMERA] Connected")

    def read_frame(self):
        if self.cap is None:
            self.connect()

        ret, frame = self.cap.read()

        if not ret:
            print("[CAMERA] Frame read failed. Reconnecting...")
            time.sleep(1)
            self.connect()
            ret, frame = self.cap.read()

        return ret, frame

    def flush_and_read_latest(self, skip_frames=15):
        ret = False
        frame = None

        for _ in range(skip_frames):
            ret, frame = self.read_frame()

        return ret, frame

    def release(self):
        if self.cap is not None:
            self.cap.release()
