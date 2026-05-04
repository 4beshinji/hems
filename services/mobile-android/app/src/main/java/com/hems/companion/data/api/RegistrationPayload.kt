package com.hems.companion.data.api

import kotlinx.serialization.Serializable

/**
 * Shape of the QR payload issued by the HEMS frontend `/mobile/devices` page.
 *
 * Generation flow: frontend calls `POST /mobile/register` (admin auth) → receives
 * one-time `device_key` + `hmac_secret` → encodes this DTO as JSON → base64 → QR.
 * The plaintext `device_key` never touches disk beyond the scanning device.
 */
@Serializable
data class RegistrationPayload(
    val device_id: Int,
    val device_key: String,
    val hmac_secret: String,
    val backend_url: String? = null,
    val character_version: String? = null,
)
