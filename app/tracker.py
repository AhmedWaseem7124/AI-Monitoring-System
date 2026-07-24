from ultralytics import YOLO


class PersonTracker:
    def __init__(self, model_path, confidence=0.5):
        print("[TRACKER] Loading YOLO model...")
        self.model = YOLO(model_path)
        self.confidence = confidence
        print("[TRACKER] Model loaded")

    def track_persons(self, frame):
        results = self.model.track(
            frame,
            persist=True,
            classes=[0],
            conf=self.confidence,
            verbose=False
        )

        persons = []

        if results[0].boxes.id is None:
            return persons

        boxes = results[0].boxes.xyxy.cpu().tolist()
        ids = results[0].boxes.id.cpu().tolist()

        for box, track_id in zip(boxes, ids):
            x1, y1, x2, y2 = box

            center_x = int((x1 + x2) / 2)
            center_y = int((y1 + y2) / 2)

            persons.append({
                "id": int(track_id),
                "box": [int(x1), int(y1), int(x2), int(y2)],
                "center": [center_x, center_y]
            })

        return persons
