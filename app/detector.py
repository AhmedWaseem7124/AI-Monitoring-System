from ultralytics import YOLO


class PersonDetector:
    def __init__(self, model_path, confidence=0.5):
        print("[DETECTOR] Loading YOLO model...")
        self.model = YOLO(model_path)
        self.confidence = confidence
        print("[DETECTOR] Model loaded")

    def detect_person(self, frame):
        results = self.model(
            frame,
            classes=[0],
            conf=self.confidence,
            verbose=False
        )

        boxes = []

        for r in results:
            for box in r.boxes:
                boxes.append(box)

        return boxes
