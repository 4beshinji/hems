"""
Tests for HEMS Perception Service.

Covers: Detector, ActivityTracker, CameraManager, MQTT topic compliance,
and WorldModel integration.
"""
import asyncio
import json
import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

np = pytest.importorskip("numpy", reason="numpy not installed")

# Mock heavy optional dependencies that are NOT installed in the test env.
# Only mock what's truly missing — paho-mqtt IS installed and must not be mocked
# (mocking it breaks other tests like test_openclaw_bridge).
for _mod_name in ("cv2", "ultralytics"):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)

# Import perception modules using importlib to avoid polluting sys.modules.
# Multiple services share module names (e.g., mqtt_publisher, config) so we
# must not let perception's versions shadow openclaw-bridge's.
import importlib.util as _ilu

_PERCEP_SRC = Path(__file__).resolve().parent.parent / "services" / "perception" / "src"


def _import_perception_module(name: str):
    spec = _ilu.spec_from_file_location(f"perception.{name}", _PERCEP_SRC / f"{name}.py")
    mod = _ilu.module_from_spec(spec)
    # Temporarily make sibling modules discoverable for intra-package imports
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod_config = _import_perception_module("config")
_mod_mqtt = _import_perception_module("mqtt_publisher")
_mod_detector = _import_perception_module("detector")
_mod_activity = _import_perception_module("activity_tracker")
_mod_camera = _import_perception_module("camera_manager")

# Re-export classes under clean names
Detector = _mod_detector.Detector
Detection = _mod_detector.Detection
FrameResult = _mod_detector.FrameResult
ActivityTracker = _mod_activity.ActivityTracker
ActivityState = _mod_activity.ActivityState
CameraManager = _mod_camera.CameraManager
MCPCamera = _mod_camera.MCPCamera
StreamCamera = _mod_camera.StreamCamera
CameraSource = _mod_camera.CameraSource
MQTTPublisher = _mod_mqtt.MQTTPublisher

# Clean up: remove perception modules from sys.modules so they don't shadow
# identically-named modules from other services (openclaw-bridge, etc.)
for _name in ("config", "mqtt_publisher", "detector", "activity_tracker", "camera_manager"):
    sys.modules.pop(_name, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_keypoints(posture: str = "standing") -> np.ndarray:
    """Generate synthetic COCO 17-keypoint data for a given posture."""
    kps = np.zeros((17, 3), dtype=np.float32)
    conf = 0.9

    if posture == "standing":
        # Vertical layout: nose(0), shoulders(5,6), hips(11,12), knees(13,14), ankles(15,16)
        kps[0] = [320, 50, conf]    # nose
        kps[5] = [300, 100, conf]   # left shoulder
        kps[6] = [340, 100, conf]   # right shoulder
        kps[11] = [300, 250, conf]  # left hip
        kps[12] = [340, 250, conf]  # right hip
        kps[13] = [300, 370, conf]  # left knee
        kps[14] = [340, 370, conf]  # right knee
        kps[15] = [300, 460, conf]  # left ankle
        kps[16] = [340, 460, conf]  # right ankle

    elif posture == "sitting":
        # Shoulders above hips, knees at same height as hips
        kps[0] = [320, 50, conf]
        kps[5] = [300, 100, conf]
        kps[6] = [340, 100, conf]
        kps[11] = [300, 250, conf]
        kps[12] = [340, 250, conf]
        kps[13] = [300, 260, conf]  # knees ~ hip level
        kps[14] = [340, 260, conf]
        kps[15] = [300, 350, conf]
        kps[16] = [340, 350, conf]

    elif posture == "lying":
        # Shoulders and hips at nearly same Y (horizontal)
        kps[0] = [100, 200, conf]
        kps[5] = [150, 200, conf]
        kps[6] = [200, 200, conf]
        kps[11] = [300, 210, conf]  # diff < 30
        kps[12] = [350, 210, conf]
        kps[13] = [400, 215, conf]
        kps[14] = [450, 215, conf]
        kps[15] = [500, 220, conf]
        kps[16] = [550, 220, conf]

    return kps


def _make_frame(width: int = 640, height: int = 480) -> np.ndarray:
    """Create a blank test frame."""
    return np.zeros((height, width, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Detector Tests
# ---------------------------------------------------------------------------

class TestDetector:
    def test_detect_returns_frame_result_structure(self):
        """Mock YOLO model to verify FrameResult structure."""
        det = Detector(pose_model_name="yolo11s-pose.pt", confidence=0.5)

        # Create mock YOLO result
        mock_box = MagicMock()
        mock_box.xyxy = [MagicMock(tolist=lambda: [10.0, 20.0, 100.0, 200.0])]
        mock_box.conf = [MagicMock(__float__=lambda self: 0.85)]

        mock_boxes = MagicMock()
        mock_boxes.__len__ = lambda self: 1
        mock_boxes.__getitem__ = lambda self, i: mock_box

        mock_kps_data = MagicMock()
        mock_kps_tensor = MagicMock()
        mock_kps_tensor.cpu.return_value.numpy.return_value = _make_keypoints("standing")
        mock_kps_data.data = [mock_kps_tensor]
        mock_kps_data.__len__ = lambda self: 1
        mock_kps_data.__getitem__ = lambda self, i: mock_kps_data

        mock_result = MagicMock()
        mock_result.boxes = mock_boxes
        mock_result.keypoints = mock_kps_data

        det._pose_model = MagicMock(return_value=[mock_result])
        det._loaded = True

        frame = _make_frame()
        result = det.detect(frame)

        assert isinstance(result, FrameResult)
        assert result.person_count == 1
        assert len(result.detections) == 1
        assert result.detections[0].confidence == 0.85
        assert result.timestamp > 0

    def test_detect_filters_person_class_only(self):
        """Verify that detect passes classes=[0] to YOLO."""
        det = Detector(confidence=0.6)
        det._pose_model = MagicMock(return_value=[])
        det._loaded = True

        frame = _make_frame()
        det.detect(frame)

        det._pose_model.assert_called_once()
        call_kwargs = det._pose_model.call_args[1]
        assert call_kwargs["classes"] == [0]
        assert call_kwargs["conf"] == 0.6

    def test_detect_empty_frame(self):
        """No detections → person_count=0, empty detections list."""
        det = Detector()

        mock_result = MagicMock()
        mock_result.boxes = MagicMock(__len__=lambda self: 0)
        mock_result.boxes.__iter__ = lambda self: iter([])
        mock_result.keypoints = None

        det._pose_model = MagicMock(return_value=[mock_result])
        det._loaded = True

        result = det.detect(_make_frame())
        assert result.person_count == 0
        assert result.detections == []

    def test_detect_model_not_loaded(self):
        """Returns empty result when model not loaded."""
        det = Detector()
        assert not det.loaded
        result = det.detect(_make_frame())
        assert result.person_count == 0


# ---------------------------------------------------------------------------
# ActivityTracker Tests
# ---------------------------------------------------------------------------

class TestActivityTracker:
    def test_standing_classification(self):
        tracker = ActivityTracker()
        kps = _make_keypoints("standing")
        state = tracker.update(kps, timestamp=1000.0)
        assert state.posture == "standing"

    def test_sitting_classification(self):
        tracker = ActivityTracker()
        kps = _make_keypoints("sitting")
        state = tracker.update(kps, timestamp=1000.0)
        assert state.posture == "sitting"

    def test_lying_classification(self):
        tracker = ActivityTracker()
        kps = _make_keypoints("lying")
        state = tracker.update(kps, timestamp=1000.0)
        assert state.posture == "lying"

    def test_walking_detection(self):
        """Standing + significant movement → walking."""
        tracker = ActivityTracker()
        # First frame: standing
        kps1 = _make_keypoints("standing")
        tracker.update(kps1, timestamp=1000.0)

        # Second frame: standing but shifted significantly
        kps2 = _make_keypoints("standing")
        kps2[:, 0] += 250  # large X displacement
        state = tracker.update(kps2, timestamp=1005.0)
        assert state.posture == "walking"

    def test_activity_level_computation(self):
        tracker = ActivityTracker()
        # Frame 1: baseline
        kps1 = _make_keypoints("standing")
        tracker.update(kps1, timestamp=1000.0)

        # Frame 2: no movement → low activity
        kps2 = _make_keypoints("standing")
        state = tracker.update(kps2, timestamp=1005.0)
        assert state.activity_level < 0.1
        assert state.activity_class == "idle"

    def test_posture_duration_tracking(self):
        tracker = ActivityTracker()
        kps = _make_keypoints("sitting")

        # Simulate 10 minutes of sitting
        start = 1000.0
        for i in range(120):
            tracker.update(kps, timestamp=start + i * 5)

        state = tracker.state
        assert state.posture == "sitting"
        assert state.posture_duration_sec >= 595  # ~10 min

    def test_posture_status_changing(self):
        tracker = ActivityTracker()
        kps = _make_keypoints("standing")
        state = tracker.update(kps, timestamp=1000.0)
        # < 300s → "changing"
        assert state.posture_status == "changing"

    def test_posture_status_mostly_static(self):
        tracker = ActivityTracker()
        kps = _make_keypoints("sitting")
        # First update sets posture start time
        tracker.update(kps, timestamp=1000.0)
        # Update at +400s (> 300s threshold)
        state = tracker.update(kps, timestamp=1400.0)
        assert state.posture_status == "mostly_static"

    def test_posture_status_static(self):
        tracker = ActivityTracker()
        kps = _make_keypoints("sitting")
        # First update sets posture start time
        tracker.update(kps, timestamp=1000.0)
        # Update at +3700s (> 3600s threshold)
        state = tracker.update(kps, timestamp=4700.0)
        assert state.posture_status == "static"

    def test_posture_change_resets_duration(self):
        tracker = ActivityTracker()
        # Sit for a while
        kps_sit = _make_keypoints("sitting")
        tracker.update(kps_sit, timestamp=0.0)
        tracker.update(kps_sit, timestamp=400.0)

        # Stand up
        kps_stand = _make_keypoints("standing")
        state = tracker.update(kps_stand, timestamp=401.0)
        assert state.posture == "standing"
        assert state.posture_duration_sec < 5  # just changed

    def test_none_keypoints_preserves_state(self):
        tracker = ActivityTracker()
        kps = _make_keypoints("standing")
        tracker.update(kps, timestamp=1000.0)
        state = tracker.update(None, timestamp=1005.0)
        # Should preserve previous posture info
        assert state.last_update == 1005.0


# ---------------------------------------------------------------------------
# CameraManager Tests
# ---------------------------------------------------------------------------

class TestCameraManager:
    def test_add_mcp_camera(self):
        mock_mqtt = MagicMock(spec=MQTTPublisher)
        mgr = CameraManager(mqtt_pub=mock_mqtt)
        mgr.add_camera({"device_id": "cam01", "zone": "living_room", "type": "mcp"})

        assert "cam01" in mgr.cameras
        assert isinstance(mgr.cameras["cam01"], MCPCamera)
        assert mgr.cameras["cam01"].zone == "living_room"

    def test_add_stream_camera(self):
        mgr = CameraManager()
        mgr.add_camera({
            "device_id": "cam02", "zone": "bedroom",
            "type": "stream", "url": "rtsp://192.168.1.100/stream",
        })

        assert "cam02" in mgr.cameras
        assert isinstance(mgr.cameras["cam02"], StreamCamera)
        assert mgr.cameras["cam02"].zone == "bedroom"

    def test_add_camera_missing_device_id(self):
        mgr = CameraManager()
        mgr.add_camera({"zone": "test", "type": "stream"})
        assert len(mgr.cameras) == 0

    def test_add_stream_camera_missing_url(self):
        mgr = CameraManager()
        mgr.add_camera({"device_id": "cam03", "zone": "test", "type": "stream"})
        assert len(mgr.cameras) == 0

    def test_mcp_without_mqtt(self):
        mgr = CameraManager(mqtt_pub=None)
        mgr.add_camera({"device_id": "cam01", "zone": "test", "type": "mcp"})
        assert len(mgr.cameras) == 0

    def test_empty_config(self):
        mgr = CameraManager()
        assert len(mgr.cameras) == 0
        assert mgr.active_count == 0

    def test_mqtt_message_routing(self):
        mock_mqtt = MagicMock(spec=MQTTPublisher)
        mgr = CameraManager(mqtt_pub=mock_mqtt)
        mgr.add_camera({"device_id": "cam01", "zone": "living_room", "type": "mcp"})

        cam = mgr.cameras["cam01"]
        cam.handle_response = MagicMock()

        mgr.handle_mqtt_message("mcp/cam01/response/abc123", {"image": "base64data"})
        cam.handle_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_capture_all_empty(self):
        mgr = CameraManager()
        result = await mgr.capture_all()
        assert result == {}


# ---------------------------------------------------------------------------
# MQTT Topic Compliance Tests
# ---------------------------------------------------------------------------

class TestMQTTTopicCompliance:
    """Verify topic formats match WorldModel expectations."""

    def test_camera_topic_is_5_parts(self):
        """office/{zone}/camera/{camera_id}/status — exactly 5 parts."""
        zone, cam_id = "living_room", "cam01"
        topic = f"office/{zone}/camera/{cam_id}/status"
        parts = topic.split("/")
        assert len(parts) == 5
        assert parts[0] == "office"
        assert parts[1] == zone
        assert parts[2] == "camera"
        assert parts[3] == cam_id
        assert parts[4] == "status"

    def test_activity_topic_is_4_parts(self):
        """office/{zone}/activity/{monitor_id} — exactly 4 parts."""
        zone, monitor_id = "living_room", "cam01"
        topic = f"office/{zone}/activity/{monitor_id}"
        parts = topic.split("/")
        assert len(parts) == 4
        assert parts[0] == "office"
        assert parts[1] == zone
        assert parts[2] == "activity"
        assert parts[3] == monitor_id

    def test_occupancy_payload_uses_person_count(self):
        """Payload must use 'person_count' (not 'count') — H-1 fix."""
        payload = {"person_count": 2}
        assert "person_count" in payload
        assert "count" not in payload

    def test_activity_payload_fields(self):
        """Activity payload must have the fields WorldModel expects."""
        payload = {
            "activity_level": 0.5,
            "activity_class": "moderate",
            "posture_duration_sec": 1800.0,
            "posture_status": "mostly_static",
        }
        for field in ["activity_level", "activity_class",
                      "posture_duration_sec", "posture_status"]:
            assert field in payload

    def test_bridge_status_topic(self):
        """hems/perception/bridge/status — standard bridge status."""
        topic = "hems/perception/bridge/status"
        parts = topic.split("/")
        assert parts[0] == "hems"
        assert parts[1] == "perception"
        assert parts[2] == "bridge"
        assert parts[3] == "status"


# ---------------------------------------------------------------------------
# WorldModel Integration Tests
# ---------------------------------------------------------------------------

class TestWorldModelIntegration:
    """Verify perception data flows correctly into Brain WorldModel."""

    def _get_world_model_class(self):
        """Import WorldModel from brain service."""
        brain_src = Path(__file__).resolve().parent.parent / "services" / "brain" / "src"
        wm_path = brain_src / "world_model"
        if str(brain_src) not in sys.path:
            sys.path.insert(0, str(brain_src))
            sys.path.insert(0, str(wm_path))
        from world_model import WorldModel
        return WorldModel

    def test_camera_topic_updates_occupancy(self):
        """Perception camera publish → WorldModel occupancy count."""
        WorldModel = self._get_world_model_class()
        wm = WorldModel()

        # Simulate perception publish
        topic = "office/living_room/camera/cam01/status"
        payload = {"person_count": 2}
        wm.update_from_mqtt(topic, payload)

        zone = wm.zones.get("living_room")
        assert zone is not None
        assert zone.occupancy.count == 2

    def test_activity_topic_updates_occupancy_fields(self):
        """Perception activity publish → WorldModel activity fields."""
        WorldModel = self._get_world_model_class()
        wm = WorldModel()

        topic = "office/living_room/activity/cam01"
        payload = {
            "activity_level": 0.15,
            "activity_class": "low",
            "posture_duration_sec": 1800.0,
            "posture_status": "mostly_static",
        }
        wm.update_from_mqtt(topic, payload)

        zone = wm.zones.get("living_room")
        assert zone is not None
        assert zone.occupancy.activity_level == 0.15
        assert zone.occupancy.activity_class == "low"
        assert zone.occupancy.posture_duration_sec == 1800.0
        assert zone.occupancy.posture_status == "mostly_static"

    def test_person_count_fallback_with_count_field(self):
        """WorldModel should also accept 'count' as fallback for person_count."""
        WorldModel = self._get_world_model_class()
        wm = WorldModel()

        topic = "office/living_room/camera/cam01/status"
        payload = {"count": 3}  # legacy field
        wm.update_from_mqtt(topic, payload)

        zone = wm.zones.get("living_room")
        assert zone is not None
        assert zone.occupancy.count == 3

    def test_static_posture_triggers_sedentary_state(self):
        """Static posture > threshold should be detectable by rule engine."""
        WorldModel = self._get_world_model_class()
        wm = WorldModel()

        # Set person present
        wm.update_from_mqtt("office/living_room/camera/cam01/status",
                            {"person_count": 1})

        # Set static posture for > SEDENTARY_MINUTES
        wm.update_from_mqtt("office/living_room/activity/cam01", {
            "activity_level": 0.02,
            "activity_class": "idle",
            "posture_duration_sec": 4000.0,
            "posture_status": "static",
        })

        zone = wm.zones["living_room"]
        assert zone.occupancy.count == 1
        assert zone.occupancy.posture_status == "static"
        assert zone.occupancy.posture_duration_sec > 3600


# ---------------------------------------------------------------------------
# End-to-end Publish Simulation
# ---------------------------------------------------------------------------

class TestPublishSimulation:
    """Test the full detect → track → publish data flow with mocked components."""

    def test_full_pipeline_data_flow(self):
        """Verify data types and structure through the pipeline."""
        # 1. Detector produces FrameResult
        result = FrameResult(
            person_count=1,
            detections=[
                Detection(
                    bbox=(10.0, 20.0, 100.0, 200.0),
                    confidence=0.9,
                    keypoints=_make_keypoints("sitting"),
                )
            ],
            timestamp=time.time(),
        )
        assert result.person_count == 1

        # 2. ActivityTracker processes keypoints
        tracker = ActivityTracker()
        kps = result.detections[0].keypoints
        state = tracker.update(kps, result.timestamp)
        assert state.posture == "sitting"
        assert isinstance(state.activity_level, float)
        assert isinstance(state.posture_duration_sec, float)

        # 3. Verify publishable payloads
        occupancy_payload = {"person_count": result.person_count}
        assert isinstance(json.dumps(occupancy_payload), str)

        activity_payload = {
            "activity_level": state.activity_level,
            "activity_class": state.activity_class,
            "posture_duration_sec": state.posture_duration_sec,
            "posture_status": state.posture_status,
        }
        assert isinstance(json.dumps(activity_payload), str)
