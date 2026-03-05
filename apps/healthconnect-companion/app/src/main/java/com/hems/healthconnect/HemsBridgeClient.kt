package com.hems.healthconnect

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * HTTP client for posting biometric data to HEMS biometric-bridge webhook.
 * Includes HMAC-SHA256 signing when webhook secret is configured.
 */
class HemsBridgeClient(
    private val bridgeUrl: String,
    private val webhookSecret: String = "",
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    /**
     * Post biometric reading to the bridge webhook endpoint.
     * @return true if successfully received (HTTP 200)
     */
    fun postReading(data: JSONObject): Boolean {
        val url = "${bridgeUrl.trimEnd('/')}/api/biometric/webhook"
        val body = data.toString().toRequestBody(JSON_MEDIA_TYPE)

        val builder = Request.Builder()
            .url(url)
            .post(body)

        // HMAC-SHA256 signature
        if (webhookSecret.isNotBlank()) {
            val signature = hmacSha256(webhookSecret, data.toString())
            builder.addHeader("X-HEMS-Signature", "sha256=$signature")
        }

        val response = client.newCall(builder.build()).execute()
        return response.use { it.isSuccessful }
    }

    private fun hmacSha256(secret: String, data: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret.toByteArray(), "HmacSHA256"))
        return mac.doFinal(data.toByteArray())
            .joinToString("") { "%02x".format(it) }
    }

    companion object {
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
    }
}
