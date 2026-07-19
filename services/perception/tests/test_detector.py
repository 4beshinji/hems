"""
Contract tests for the RTMO Detector — pure unit, no rtmlib/onnxruntime needed.

Pins the COCO-17 (17,3) + bbox + person_count contract that activity_tracker and
main depend on, and the RTMO zero-sentinel handling (RTMO returns a single
zero-filled "person" when a frame has no detection).
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detector import Detector, FrameResult


class _StubRTMO:
    """Mimics rtmlib.RTMO.__call__ → (keypoints (N,17,2), scores (N,17))."""

    def __init__(self, keypoints, scores):
        self._kp = keypoints
        self._sc = scores

    def __call__(self, frame):
        return self._kp, self._sc


def _make_detector(keypoints, scores) -> Detector:
    det = Detector(pose_model_name="stub.onnx", confidence=0.5)
    det._pose_model = _StubRTMO(keypoints, scores)
    det._loaded = True
    return det


_FRAME = np.zeros((480, 640, 3), dtype=np.uint8)


def test_single_person_contract():
    kp = np.zeros((1, 17, 2), dtype=np.float32)
    kp[0, :, 0] = np.linspace(100, 200, 17)  # x
    kp[0, :, 1] = np.linspace(50, 300, 17)  # y
    sc = np.full((1, 17), 0.9, dtype=np.float32)

    result = _make_detector(kp, sc).detect(_FRAME)

    assert isinstance(result, FrameResult)
    assert result.person_count == 1
    d = result.detections[0]
    assert d.keypoints.shape == (17, 3)  # COCO-17 contract
    assert len(d.bbox) == 4
    x1, y1, x2, y2 = d.bbox
    assert x1 <= x2 and y1 <= y2
    assert 0.0 <= d.confidence <= 1.0


def test_no_person_sentinel_dropped():
    kp = np.zeros((1, 17, 2), dtype=np.float32)
    sc = np.zeros((1, 17), dtype=np.float32)

    result = _make_detector(kp, sc).detect(_FRAME)

    assert result.person_count == 0
    assert result.detections == []


def test_multi_person_count():
    kp = np.zeros((2, 17, 2), dtype=np.float32)
    kp[:, :, 0] = np.linspace(10, 100, 17)
    kp[:, :, 1] = np.linspace(10, 200, 17)
    sc = np.full((2, 17), 0.8, dtype=np.float32)

    result = _make_detector(kp, sc).detect(_FRAME)

    assert result.person_count == 2


def test_not_loaded_returns_empty():
    det = Detector(pose_model_name="stub.onnx")
    result = det.detect(_FRAME)
    assert result.person_count == 0
    assert result.detections == []
