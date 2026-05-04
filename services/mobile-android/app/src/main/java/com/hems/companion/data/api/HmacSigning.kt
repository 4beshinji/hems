package com.hems.companion.data.api

import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * HMAC-SHA256 signing — must match backend ``hmac_util.compute_signature``.
 * Header value is always ``sha256=<hex>``.
 */
object HmacSigning {
    private const val ALG = "HmacSHA256"

    fun sign(secret: String, body: ByteArray): String {
        val mac = Mac.getInstance(ALG)
        mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), ALG))
        return mac.doFinal(body).joinToString("") { "%02x".format(it) }
    }

    fun header(secret: String, body: ByteArray): String = "sha256=${sign(secret, body)}"
}
