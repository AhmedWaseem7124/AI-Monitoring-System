import os
import json
import cv2
import numpy as np
from datetime import datetime


class UnknownManager:
    def __init__(
        self,
        base_dir="unknown_faces",
        threshold=0.55,
        max_embeddings_per_unknown=5
    ):
        self.base_dir = base_dir
        self.embeddings_dir = os.path.join(base_dir, "embeddings")
        self.snapshots_dir = os.path.join(base_dir, "snapshots")
        self.index_file = os.path.join(base_dir, "unknown_index.json")

        self.threshold = threshold
        self.max_embeddings_per_unknown = max_embeddings_per_unknown

        os.makedirs(self.embeddings_dir, exist_ok=True)
        os.makedirs(self.snapshots_dir, exist_ok=True)

        self.unknowns = {}
        self.load_index()

        print(f"[UNKNOWN] Loaded {len(self.unknowns)} unknown profiles")

    def load_index(self):
        if os.path.exists(self.index_file):
            with open(self.index_file, "r") as f:
                self.unknowns = json.load(f)
        else:
            self.unknowns = {}

    def save_index(self):
        with open(self.index_file, "w") as f:
            json.dump(self.unknowns, f, indent=4)

    def _now(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _next_unknown_id(self):
        if not self.unknowns:
            return "UNKNOWN_001"

        nums = []

        for key in self.unknowns.keys():
            try:
                nums.append(int(key.split("_")[1]))
            except Exception:
                pass

        next_num = max(nums) + 1 if nums else 1
        return f"UNKNOWN_{next_num:03d}"

    def _load_embeddings(self, unknown_id):
        folder = os.path.join(self.embeddings_dir, unknown_id)

        if not os.path.exists(folder):
            return []

        embeddings = []

        for file_name in os.listdir(folder):
            if file_name.endswith(".npy"):
                emb = np.load(os.path.join(folder, file_name))
                embeddings.append(emb)

        return embeddings

    def match_or_create(self, embedding, snapshot_frame=None):
        embedding = embedding / np.linalg.norm(embedding)

        best_id = None
        best_score = -1

        for unknown_id in self.unknowns.keys():
            saved_embeddings = self._load_embeddings(unknown_id)

            for saved_emb in saved_embeddings:
                saved_emb = saved_emb / np.linalg.norm(saved_emb)
                score = float(np.dot(embedding, saved_emb))

                if score > best_score:
                    best_score = score
                    best_id = unknown_id

        if best_id is not None and best_score >= self.threshold:
            self._update_existing_unknown(
                unknown_id=best_id,
                embedding=embedding,
                snapshot_frame=snapshot_frame,
                score=best_score
            )

            print(
                f"[UNKNOWN] Repeat visitor matched: {best_id} | score={best_score:.3f}"
            )

            return {
                "unknown_id": best_id,
                "is_repeat": True,
                "score": best_score,
                "visits": self.unknowns[best_id]["visits"]
            }

        new_id = self._create_new_unknown(
            embedding=embedding,
            snapshot_frame=snapshot_frame,
            score=best_score
        )

        print(f"[UNKNOWN] New visitor created: {new_id}")

        return {
            "unknown_id": new_id,
            "is_repeat": False,
            "score": best_score,
            "visits": 1
        }

    def _create_new_unknown(self, embedding, snapshot_frame=None, score=-1):
        unknown_id = self._next_unknown_id()
        now = self._now()

        self.unknowns[unknown_id] = {
            "first_seen": now,
            "last_seen": now,
            "visits": 1,
            "last_similarity": round(float(score), 3)
        }

        self._add_embedding(unknown_id, embedding)

        if snapshot_frame is not None:
            self._save_snapshot(unknown_id, snapshot_frame)

        self.save_index()

        return unknown_id

    def _update_existing_unknown(self, unknown_id, embedding, snapshot_frame=None, score=-1):
        now = self._now()

        self.unknowns[unknown_id]["last_seen"] = now
        self.unknowns[unknown_id]["visits"] = (
            self.unknowns[unknown_id].get("visits", 0) + 1
        )
        self.unknowns[unknown_id]["last_similarity"] = round(float(score), 3)

        self._add_embedding(unknown_id, embedding)

        if snapshot_frame is not None:
            self._save_snapshot(unknown_id, snapshot_frame)

        self.save_index()

    def _add_embedding(self, unknown_id, embedding):
        folder = os.path.join(self.embeddings_dir, unknown_id)
        os.makedirs(folder, exist_ok=True)

        existing = [
            f for f in os.listdir(folder)
            if f.endswith(".npy")
        ]

        if len(existing) >= self.max_embeddings_per_unknown:
            return

        file_path = os.path.join(
            folder,
            f"embedding_{len(existing) + 1}.npy"
        )

        np.save(file_path, embedding)

    def _save_snapshot(self, unknown_id, frame):
        folder = os.path.join(self.snapshots_dir, unknown_id)
        os.makedirs(folder, exist_ok=True)

        count = len([
            f for f in os.listdir(folder)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ])

        file_path = os.path.join(
            folder,
            f"snapshot_{count + 1}.jpg"
        )

        cv2.imwrite(file_path, frame)

    def get_all_unknowns(self):
        return self.unknowns
