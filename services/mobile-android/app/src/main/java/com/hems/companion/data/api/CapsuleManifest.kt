package com.hems.companion.data.api

import kotlinx.serialization.Serializable

/**
 * Mirrors backend ``schemas.VoiceCapsuleManifest`` — snake_case matches.
 */
@Serializable
data class CapsuleManifest(
    val capsule_id: String,
    val character_version: String? = null,
    val generated_at: String? = null,
    val expires_at: String? = null,
    val clips: List<CapsuleClip> = emptyList(),
    val generic_bank: List<CapsuleBankClip> = emptyList(),
)

@Serializable
data class CapsuleClip(
    val id: String,
    val trigger: CapsuleTrigger,
    val audio_url: String,
    val transcript: String? = null,
    val priority: Int = 5,
    val tone: String? = "neutral",
    val expires_at: String? = null,
    val tags: List<String> = emptyList(),
)

@Serializable
data class CapsuleBankClip(
    val id: String,
    val tag: String,
    val audio_url: String,
    val transcript: String? = null,
)

@Serializable
data class CapsuleTrigger(
    val kind: String,                  // time | pre_event | geofence | biometric_threshold
    val at: String? = null,
    val absolute_ts: Long? = null,
    val event_id: String? = null,
    val offset_min: Int? = null,
    val zone: String? = null,
    val event: String? = null,
    val cooldown_min: Int? = null,
    val lat: Double? = null,
    val lon: Double? = null,
    val radius_m: Int? = null,
    val metric: String? = null,
    val op: String? = null,
    val value: Double? = null,
)

@Serializable
data class CapsulePlayAck(
    val capsule_id: String,
    val clip_id: String,
    val played_at: String,             // ISO-8601
    val trigger_drift_sec: Int? = null,
    val context_json: String? = null,
)
