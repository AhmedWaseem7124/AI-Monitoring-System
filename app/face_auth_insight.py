import os
import cv2
import numpy as np
from insightface.app import FaceAnalysis


class InsightFaceAuthenticator:
    def __init__(self, known_faces_dir="known_faces", threshold=0.40):
        self.known_faces_dir = known_faces_dir
        self.threshold = threshold
        self.known_embeddings = []
        self.known_names = []

        print("[INSIGHTFACE] Loading model...")
        self.app = FaceAnalysis(
            name="buffalo_s",
            providers=["CPUExecutionProvider"]
        )

        self.app.prepare(
            ctx_id=-1,
            det_size=(640, 640)
        )

        print("[INSIGHTFACE] Model loaded")

        print("[INSIGHTFACE] Loading known faces...")
        self.load_known_faces()
        print(
            f"[INSIGHTFACE] Loaded {len(self.known_embeddings)} known embeddings"
        )

    def load_known_faces(self):
        if not os.path.exists(self.known_faces_dir):
            print("[INSIGHTFACE] known_faces folder not found")
            return

        for person_name in os.listdir(self.known_faces_dir):
            person_folder = os.path.join(
                self.known_faces_dir,
                person_name
            )

            if not os.path.isdir(person_folder):
                continue

            for file_name in os.listdir(person_folder):
                if not file_name.lower().endswith(
                    (".jpg", ".jpeg", ".png")
                ):
                    continue

                image_path = os.path.join(
                    person_folder,
                    file_name
                )

                try:
                    img = cv2.imread(image_path)

                    if img is None:
                        print(
                            f"[INSIGHTFACE WARNING] Could not read {image_path}"
                        )
                        continue

                    faces = self.app.get(img)

                    if len(faces) == 0:
                        print(
                            f"[INSIGHTFACE WARNING] No face found in {image_path}"
                        )
                        continue

                    face = faces[0]

                    embedding = face.embedding
                    embedding = embedding / np.linalg.norm(embedding)

                    self.known_embeddings.append(embedding)
                    self.known_names.append(person_name.upper())

                    print(
                        f"[INSIGHTFACE] Loaded {person_name}: {file_name}"
                    )

                except Exception as e:
                    print(
                        f"[INSIGHTFACE ERROR] {image_path}: {e}"
                    )

    def recognize_all(self, frame):
        """
        Returns:
        [
            {
                "name": "AHMED" or "UNKNOWN",
                "embedding": numpy array,
                "score": similarity score
            }
        ]
        """

        try:
            faces = self.app.get(frame)

            if len(faces) == 0:
                return []

            detected = []

            for face in faces:
                embedding = face.embedding
                embedding = embedding / np.linalg.norm(embedding)

                best_name = "UNKNOWN"
                best_score = -1

                for known_embedding, known_name in zip(
                    self.known_embeddings,
                    self.known_names
                ):
                    score = np.dot(
                        embedding,
                        known_embedding
                    )

                    if score > best_score:
                        best_score = score
                        best_name = known_name

                if best_score >= self.threshold:
                    final_name = best_name
                else:
                    final_name = "UNKNOWN"

                print(
                    f"[INSIGHTFACE] Best match: {best_name} | score={best_score:.3f} | final={final_name}"
                )

                detected.append(
                    {
                        "name": final_name,
                        "embedding": embedding,
                        "score": float(best_score)
                    }
                )

            return detected

        except Exception as e:
            print(
                f"[INSIGHTFACE ERROR] Recognition failed: {e}"
            )
            return []


    def reload_known_faces(self):
        print("[INSIGHTFACE] Reloading known faces...")

        self.known_embeddings = []
        self.known_names = []

        self.load_known_faces()

        print(f"[INSIGHTFACE] Reload complete: {len(self.known_embeddings)} embeddings loaded")
