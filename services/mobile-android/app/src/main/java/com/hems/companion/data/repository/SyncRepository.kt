package com.hems.companion.data.repository

import com.hems.companion.data.api.BackendApi
import com.hems.companion.data.api.HmacSigning
import com.hems.companion.data.api.MobileStatePayload
import com.hems.companion.data.preferences.DeviceCredentialsStore
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.first
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * Submit a [MobileStatePayload] to the backend. Signs the raw body with the
 * per-device HMAC secret and posts to ``<backend_url>/mobile/state/webhook``.
 *
 * The repository is deliberately thin — there is no retry here. WorkManager
 * owns retry (exponential backoff) and the buffer eviction policy prevents
 * unbounded growth when offline.
 */
@Singleton
class SyncRepository @Inject constructor(
    private val api: BackendApi,
    private val store: DeviceCredentialsStore,
    private val json: Json,
) {
    sealed class Outcome {
        data object Ok : Outcome()
        data object NotRegistered : Outcome()
        data class Http(val code: Int, val message: String?) : Outcome()
        data class Network(val cause: Throwable) : Outcome()
    }

    suspend fun submit(payload: MobileStatePayload): Outcome {
        val creds = store.credentials.first() ?: return Outcome.NotRegistered

        val bodyBytes = json
            .encodeToString(MobileStatePayload.serializer(), payload)
            .toByteArray(Charsets.UTF_8)
        val signature = HmacSigning.header(creds.hmacSecret, bodyBytes)
        val url = "${creds.backendUrl.trimEnd('/')}/mobile/state/webhook"

        return runCatching {
            api.submitState(
                url = url,
                deviceKey = "Bearer ${creds.deviceKey}",
                signature = signature,
                body = bodyBytes.toRequestBody(JSON_MEDIA),
            )
        }.fold(
            onSuccess = { Outcome.Ok },
            onFailure = { t ->
                when (t) {
                    is retrofit2.HttpException -> Outcome.Http(t.code(), t.message())
                    else -> Outcome.Network(t)
                }
            },
        )
    }

    companion object {
        private val JSON_MEDIA = "application/json".toMediaType()
    }
}
