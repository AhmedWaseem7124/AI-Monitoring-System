import os
import cv2
import numpy as np
import face_recognition


class FaceAuthenticator:
    def __init__(self, known_faces_dir="known_faces", tolerance=0.6):
        self.known_faces_dir = known_faces_dir
        self.tolerance = tolerance
        self.known_encodings = []
        self.known_names = []

        print("[FACE] Loading known faces...")
        self.load_known_faces()
        print(f"[FACE] Loaded {len(self.known_encodings)} known face encodings")

    def load_known_faces(self):
        for person_name in os.listdir(self.known_faces_dir):
            person_folder = os.path.join(self.known_faces_dir, person_name)

            if not os.path.isdir(person_folder):
                continue

            for file_name in os.listdir(person_folder):
                if not file_name.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue

                image_path = os.path.join(person_folder, file_name)

                try:
                    image = face_recognition.load_image_file(image_path)
                    image = np.ascontiguousarray(image)

                    encodings = face_recognition.face_encodings(image)

                    if encodings:
                        self.known_encodings.append(encodings[0])
                        self.known_names.append(person_name.upper())
                        print(f"[FACE] Loaded {person_name}: {file_name}")

                except Exception as e:
                    print(f"[FACE ERROR] {image_path}: {e}")

    def recognize_all(self, frame):
        try:
            small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            rgb_frame = np.ascontiguousarray(rgb_frame, dtype=np.uint8)

            face_locations = face_recognition.face_locations(
                rgb_frame,
                model="hog"
            )

            if not face_locations:
                return []

            face_encodings = face_recognition.face_encodings(
                rgb_frame,
                face_locations,
                num_jitters=0
            )

            detected_names = []

            for face_encoding in face_encodings:
                name = "UNKNOWN"

                if self.known_encodings:
                    distances = face_recognition.face_distance(
                        self.known_encodings,
                        face_encoding
                    )

                    best_index = np.argmin(distances)

                    if distances[best_index] <= self.tolerance:
                        name = self.known_names[best_index]

                detected_names.append(name)

            return detected_names

        except Exception as e:
            print(f"[FACE ERROR] Recognition failed: {e}")
            return []
