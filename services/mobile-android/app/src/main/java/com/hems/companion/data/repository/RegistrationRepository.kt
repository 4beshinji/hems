package com.hems.companion.data.repository

import android.util.Base64
import com.hems.companion.data.api.RegistrationPayload
import com.hems.companion.data.preferences.DeviceCredentials
import com.hems.companion.data.preferences.DeviceCredentialsStore
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.json.Json

@Singleton
class RegistrationRepository @Inject constructor(
    private val store: DeviceCredentialsStore,
    private val json: Json,
) {
    val credentials: Flow<DeviceCredentials?> = store.credentials

    /**
     * Parse a QR payload (raw JSON OR base64-wrapped JSON) and persist the
     * resulting credentials. Returns the saved credentials on success.
     */
    suspend fun registerFromQr(raw: String): Result<DeviceCredentials> = runCatching {
        val text = decodeBase64IfWrapped(raw).trim()
        val payload = json.decodeFromString(RegistrationPayload.serializer(), text)
        val backendUrl = payload.backend_url
            ?: throw IllegalArgumentException("backend_url missing from QR payload")
        val creds = DeviceCredentials(
            deviceId = payload.device_id,
            deviceKey = payload.device_key,
            hmacSecret = payload.hmac_secret,
            backendUrl = backendUrl,
            characterVersion = payload.character_version,
        )
        store.save(creds)
        creds
    }

    suspend fun reset() = store.clear()

    /**
     * The frontend may emit either raw JSON or base64(JSON) depending on the
     * generator. Try base64 first; fall back to the input when it doesn't
     * look like base64 or doesn't decode to JSON.
     */
    private fun decodeBase64IfWrapped(raw: String): String {
        if (raw.startsWith("{")) return raw
        return try {
            val bytes = Base64.decode(raw, Base64.DEFAULT)
            val decoded = String(bytes, Charsets.UTF_8)
            if (decoded.startsWith("{")) decoded else raw
        } catch (_: IllegalArgumentException) {
            raw
        }
    }
}
