package com.hems.companion.data.repository

import android.content.Context
import com.hems.companion.data.api.BackendApi
import com.hems.companion.data.api.CapsuleManifest
import com.hems.companion.data.api.CapsulePlayAck
import com.hems.companion.data.preferences.CapsuleStore
import com.hems.companion.data.preferences.DeviceCredentialsStore
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.time.Instant
import java.time.format.DateTimeFormatter
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.first

@Singleton
class CapsuleRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val api: BackendApi,
    private val store: CapsuleStore,
    private val credentials: DeviceCredentialsStore,
) {

    val manifest get() = store.manifest

    private val cacheDir: File by lazy {
        File(context.filesDir, "capsule").apply { mkdirs() }
    }

    suspend fun fetchAndDownload(): Result<CapsuleManifest> = runCatching {
        val creds = credentials.credentials.first()
            ?: throw IllegalStateException("not registered")
        val auth = "Bearer ${creds.deviceKey}"
        val latestUrl = "${creds.backendUrl.trimEnd('/')}/mobile/voice-capsule/latest"
        val manifest = api.getLatestCapsule(latestUrl, auth)

        // Download any clip whose local copy is missing.
        val allUrls = (manifest.clips.map { it.audio_url } +
            manifest.generic_bank.map { it.audio_url }).filter { it.isNotBlank() }
        for (audioPath in allUrls.toSet()) {
            val local = localFileFor(audioPath)
            if (local.exists() && local.length() > 0) continue
            val absolute = if (audioPath.startsWith("http")) audioPath
                else "${creds.backendUrl.trimEnd('/')}$audioPath"
            val body = api.downloadAudio(absolute, auth)
            body.byteStream().use { input ->
                local.outputStream().use { out -> input.copyTo(out) }
            }
        }
        store.saveManifest(manifest)
        manifest
    }

    /** Resolve the on-disk file a given clip's audio_url was cached to. */
    fun localFileFor(audioUrl: String): File {
        val fname = audioUrl.substringAfterLast('/').ifEmpty { "clip.mp3" }
        return File(cacheDir, fname)
    }

    suspend fun ack(capsuleId: String, clipId: String, triggerDriftSec: Int? = null) {
        val creds = credentials.credentials.first() ?: return
        val url = "${creds.backendUrl.trimEnd('/')}/mobile/voice-capsule/ack"
        api.ackPlayback(
            url = url,
            deviceKey = "Bearer ${creds.deviceKey}",
            ack = CapsulePlayAck(
                capsule_id = capsuleId,
                clip_id = clipId,
                played_at = DateTimeFormatter.ISO_INSTANT.format(Instant.now()),
                trigger_drift_sec = triggerDriftSec,
            ),
        )
    }
}
