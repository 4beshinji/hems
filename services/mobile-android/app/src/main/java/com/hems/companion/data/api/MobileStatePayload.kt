package com.hems.companion.data.api

import kotlinx.serialization.Serializable

/**
 * Mirrors backend ``schemas.MobileStateWebhookPayload``. Single batch sent
 * to ``/mobile/state/webhook`` — any subset of fields may be omitted.
 *
 * Keep property names identical to the backend (snake_case already matches).
 */
@Serializable
data class MobileStatePayload(
    val ts: String,  // ISO-8601 with offset, client-local
    val location: MobileLocation? = null,
    val activity: MobileActivity? = null,
    val biometrics: MobileBiometrics? = null,
    val battery_pct: Int? = null,
    val app_foreground: Boolean? = null,
)

@Serializable
data class MobileLocation(
    val lat: Double,
    val lon: Double,
    val accuracy_m: Double? = null,
    val speed_mps: Double? = null,
    val heading_deg: Double? = null,
    val provider: String? = null,
)

@Serializable
data class MobileActivity(
    val kind: String,  // still | walking | running | in_vehicle | on_bicycle | unknown
    val confidence: Int? = null,
)

@Serializable
data class MobileBiometrics(
    val heart_rate: Int? = null,
    val spo2: Int? = null,
    val steps: Int? = null,
    val stress_level: Int? = null,
    val sleep_duration_minutes: Int? = null,
)
