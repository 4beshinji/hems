package com.hems.companion.data.preferences

import kotlinx.serialization.Serializable

@Serializable
data class DeviceCredentials(
    val deviceId: Int,
    val deviceKey: String,
    val hmacSecret: String,
    val backendUrl: String,
    val characterVersion: String?,
)
