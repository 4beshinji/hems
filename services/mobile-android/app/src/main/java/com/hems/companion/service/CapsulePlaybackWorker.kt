package com.hems.companion.service

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.hems.companion.data.repository.CapsuleRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Plays a single clip end-to-end via MediaPlayer, then posts a playback
 * ack back to the backend. Runs as a one-shot worker triggered by
 * [CapsulePlaybackReceiver].
 */
@HiltWorker
class CapsulePlaybackWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val repo: CapsuleRepository,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val capsuleId = inputData.getString(KEY_CAPSULE_ID) ?: return Result.failure()
        val clipId = inputData.getString(KEY_CLIP_ID) ?: return Result.failure()
        val audioUrl = inputData.getString(KEY_AUDIO_URL) ?: return Result.failure()
        val scheduledAt = inputData.getLong(KEY_SCHEDULED_AT_MS, 0L)

        val file = repo.localFileFor(audioUrl)
        if (!file.exists() || file.length() == 0L) {
            return Result.failure()
        }

        val played = withTimeoutOrNull(MAX_CLIP_DURATION_MS) { playFile(file.absolutePath) }
            ?: false
        if (!played) return Result.failure()

        val drift = if (scheduledAt > 0) ((System.currentTimeMillis() - scheduledAt) / 1000).toInt()
            else null
        runCatching { repo.ack(capsuleId, clipId, drift) }
        return Result.success()
    }

    private suspend fun playFile(path: String): Boolean {
        val done = CompletableDeferred<Boolean>()
        val player = MediaPlayer().apply {
            setAudioAttributes(
                AudioAttributes.Builder()
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .setUsage(AudioAttributes.USAGE_ASSISTANT)
                    .build()
            )
            setOnCompletionListener { done.complete(true) }
            setOnErrorListener { _, _, _ ->
                done.complete(false)
                true
            }
        }
        return try {
            player.setDataSource(path)
            player.prepare()
            player.start()
            done.await()
        } catch (_: Exception) {
            false
        } finally {
            runCatching { player.release() }
        }
    }

    companion object {
        const val TAG = "capsule-playback"
        const val KEY_CAPSULE_ID = "capsule_id"
        const val KEY_CLIP_ID = "clip_id"
        const val KEY_AUDIO_URL = "audio_url"
        const val KEY_SCHEDULED_AT_MS = "scheduled_at_ms"

        /** Hard upper bound so a stuck player never holds the worker forever. */
        private const val MAX_CLIP_DURATION_MS = 120_000L
    }
}
