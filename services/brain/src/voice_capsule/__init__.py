"""Voice capsule — pre-synth clips delivered to the mobile companion.

P2 scope: time-trigger clips only (morning_greet, weather_morning, schedule
reminders at absolute times) plus a small generic bank. Event-classified
pre_event, geofence and biometric-threshold triggers are P3+.
"""

from .builder import CapsuleBuilder, ClipSpec

__all__ = ["CapsuleBuilder", "ClipSpec"]
