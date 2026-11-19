"""
SORT — Simple Online and Realtime Tracker
Wraps each detection in a Kalman filter; assigns persistent IDs across frames.
State vector: [cx, cy, s, r, dcx, dcy, ds]  (s=area, r=aspect ratio)
"""
from __future__ import annotations

import numpy as np
from filterpy.kalman import KalmanFilter
from scipy.optimize import linear_sum_assignment


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    xx1 = max(a[0], b[0]); yy1 = max(a[1], b[1])
    xx2 = min(a[2], b[2]); yy2 = min(a[3], b[3])
    inter = max(0, xx2 - xx1) * max(0, yy2 - yy1)
    area_a = (a[2]-a[0]) * (a[3]-a[1])
    area_b = (b[2]-b[0]) * (b[3]-b[1])
    return inter / (area_a + area_b - inter + 1e-6)


def _to_z(bbox: np.ndarray) -> np.ndarray:
    """[x1,y1,x2,y2] → [cx,cy,s,r]"""
    w = bbox[2] - bbox[0]; h = bbox[3] - bbox[1]
    return np.array([[bbox[0]+w/2], [bbox[1]+h/2], [w*h], [w/(h+1e-6)]])


def _to_bbox(x: np.ndarray) -> np.ndarray:
    """Kalman state → [x1,y1,x2,y2]"""
    w = np.sqrt(abs(float(x[2, 0]) * float(x[3, 0])))
    h = abs(float(x[2, 0])) / (w + 1e-6)
    cx, cy = float(x[0, 0]), float(x[1, 0])
    return np.array([cx - w/2, cy - h/2, cx + w/2, cy + h/2])


class _KalmanTrack:
    _next_id = 0

    def __init__(self, bbox: np.ndarray, score: float = 0.0) -> None:
        kf = KalmanFilter(dim_x=7, dim_z=4)
        kf.F = np.eye(7)
        kf.F[0, 4] = kf.F[1, 5] = kf.F[2, 6] = 1.0
        kf.H = np.zeros((4, 7)); np.fill_diagonal(kf.H, 1.0)
        kf.R[2:, 2:] *= 10.0
        kf.P[4:, 4:] *= 1000.0
        kf.P *= 10.0
        kf.Q[-1, -1] *= 0.01
        kf.Q[4:, 4:] *= 0.01
        kf.x[:4] = _to_z(bbox)
        self.kf = kf
        self.id: int = _KalmanTrack._next_id
        _KalmanTrack._next_id += 1
        self.hits = 1
        self.hit_streak = 1
        self.age = 0
        self.time_since_update = 0
        self.last_score: float = score

    def predict(self) -> np.ndarray:
        if float(self.kf.x[6, 0]) + float(self.kf.x[2, 0]) <= 0:
            self.kf.x[6, 0] = 0.0
        self.kf.predict()
        self.age += 1
        if self.time_since_update > 0:
            self.hit_streak = 0
        self.time_since_update += 1
        return _to_bbox(self.kf.x)

    def update(self, bbox: np.ndarray) -> None:
        self.kf.update(_to_z(bbox))
        self.hits += 1
        self.hit_streak += 1
        self.time_since_update = 0

    def state(self) -> np.ndarray:
        return _to_bbox(self.kf.x)


class Sort:
    """
    Multi-object tracker using Kalman filter + Hungarian assignment.

    max_age   — frames to keep a track alive without a detection match
    min_hits  — detection hits needed before a track is returned
    iou_threshold — minimum IoU to consider a detection-track pair a match
    """

    def __init__(self, max_age: int = 3, min_hits: int = 1,
                 iou_threshold: float = 0.20) -> None:
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self._tracks: list[_KalmanTrack] = []
        self._frame = 0

    def reset(self) -> None:
        self._tracks.clear()
        self._frame = 0

    def advance_camera(self, motion, frame_shape) -> None:
        """
        Moves every track into the new frame's coordinates before matching.

        Call once per frame, before `update`, with the camera motion from the
        previous frame to this one (services/egomotion.CameraMotion). From a
        moving drone a person lying still slides across the image at the
        drone's speed; at one detection frame a second that is often further
        than the box is wide, so without this the IoU match failed and the
        same person got a new ID every frame or two - which restarted the
        stillness window each time. A failed estimate (`ok` False) leaves the
        tracks as they are.
        """
        if not getattr(motion, "ok", False) or not self._tracks:
            return
        cx0, cy0 = frame_shape[1] / 2.0, frame_shape[0] / 2.0

        def move(px: float, py: float) -> tuple[float, float]:
            return motion.apply(px, py, cx0, cy0)

        for t in self._tracks:
            x = t.kf.x
            x1, y1, x2, y2 = _to_bbox(x)
            corners = [move(x1, y1), move(x2, y1), move(x2, y2), move(x1, y2)]
            xs, ys = [c[0] for c in corners], [c[1] for c in corners]
            nx1, ny1, nx2, ny2 = min(xs), min(ys), max(xs), max(ys)
            if nx2 - nx1 < 1 or ny2 - ny1 < 1:
                continue
            old_area = max(float(x[2, 0]), 1e-6)
            cx, cy = float(x[0, 0]), float(x[1, 0])
            # Image velocity turns and stretches with the view: carry its tip too.
            tip, centre = move(cx + float(x[4, 0]), cy + float(x[5, 0])), move(cx, cy)
            x[:4] = _to_z(np.array([nx1, ny1, nx2, ny2]))
            x[4, 0], x[5, 0] = tip[0] - centre[0], tip[1] - centre[1]
            x[6, 0] *= float(x[2, 0]) / old_area

    def update(self, dets: np.ndarray) -> np.ndarray:
        """
        dets   : float32 array [N, 5] — [x1, y1, x2, y2, score]
        returns: float32 array [M, 6] — [x1, y1, x2, y2, score, track_id]
        """
        self._frame += 1

        # Step 1 — predict all existing tracks
        preds = np.array([t.predict() for t in self._tracks]) if self._tracks else np.empty((0, 4))

        # Step 2 — associate detections ↔ predicted positions
        matched, unmatched_dets = self._associate(dets, preds)

        # Step 3 — update matched tracks
        for d_idx, t_idx in matched:
            self._tracks[t_idx].update(dets[d_idx, :4])

        # Step 4 — spawn new tracks for unmatched detections
        for d_idx in unmatched_dets:
            self._tracks.append(_KalmanTrack(dets[d_idx, :4], float(dets[d_idx, 4])))

        # Step 5 — collect output and prune dead tracks
        out: list[list[float]] = []
        alive: list[_KalmanTrack] = []
        for t in self._tracks:
            if t.time_since_update <= self.max_age:
                alive.append(t)
                if t.hit_streak >= self.min_hits or self._frame <= self.min_hits:
                    box = t.state()
                    # use last known detection score; update if matched this frame
                    score = t.last_score
                    for d_idx, t_idx in matched:
                        if self._tracks[t_idx] is t:
                            score = float(dets[d_idx, 4])
                            t.last_score = score
                    out.append([*box.tolist(), score, float(t.id)])
        self._tracks = alive

        return np.array(out, dtype=np.float32) if out else np.empty((0, 6), dtype=np.float32)

    def _associate(self, dets: np.ndarray, trks: np.ndarray
                   ) -> tuple[list[tuple[int, int]], list[int]]:
        if len(trks) == 0:
            return [], list(range(len(dets)))
        if len(dets) == 0:
            return [], []

        iou_mat = np.zeros((len(dets), len(trks)), dtype=np.float32)
        for d in range(len(dets)):
            for t in range(len(trks)):
                iou_mat[d, t] = _iou(dets[d, :4], trks[t])

        row_ind, col_ind = linear_sum_assignment(-iou_mat)

        matched: list[tuple[int, int]] = []
        unmatched_dets = list(range(len(dets)))

        for r, c in zip(row_ind, col_ind):
            if iou_mat[r, c] >= self.iou_threshold:
                matched.append((int(r), int(c)))
                if r in unmatched_dets:
                    unmatched_dets.remove(r)

        return matched, unmatched_dets
