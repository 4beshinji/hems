package com.hems.companion.data.api

import kotlinx.serialization.Serializable
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Streaming
import retrofit2.http.Url

/**
 * Thin Retrofit surface for the HEMS backend mobile routes.
 *
 * The base URL is discovered from the QR payload, so callers pass a fully
 * qualified URL with every request — there is no singleton base URL.
 */
interface BackendApi {
    @POST
    suspend fun submitState(
        @Url url: String,
        @Header("Authorization") deviceKey: String,
        @Header("X-HEMS-Signature") signature: String,
        @Body body: RequestBody,
    ): StateWebhookResponse

    @GET
    suspend fun getLatestCapsule(
        @Url url: String,
        @Header("Authorization") deviceKey: String,
    ): CapsuleManifest

    @GET
    @Streaming
    suspend fun downloadAudio(
        @Url url: String,
        @Header("Authorization") deviceKey: String,
    ): ResponseBody

    @POST
    suspend fun ackPlayback(
        @Url url: String,
        @Header("Authorization") deviceKey: String,
        @Body ack: CapsulePlayAck,
    )
}

@Serializable
data class StateWebhookResponse(
    val received: Boolean,
    val published_topics: List<String> = emptyList(),
)
