package com.hems.companion.service

import android.content.Context
import androidx.work.Data
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.hems.companion.data.api.CapsuleClip
import com.hems.companion.data.api.MobileBiometrics
import com.hems.companion.data.preferences.CapsuleStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking

/**
 * Evaluates ``biometric_threshold`` capsule clips against incoming biometric
 * readings and enqueues playback when a threshold is crossed.
 *
 * Call [onBiometrics] from any producer (Health Connect observer, watch
 * sync, etc.) — the evaluator resolves the current manifest lazily so new
 * downloads pick up without wiring.
 *
 * Cooldown per clip is stored in SharedPreferences to avoid a rapid-fire
 * re-trigger when a reading sits just above the threshold for minutes.
 */
@Singleton
class BiometricEvaluator @Inject constructor(
    @ApplicationContext private val appContext: Context,
    private val store: CapsuleStore,
) {

    fun onBiometrics(reading: MobileBiometrics) {
        val manifest = runBlocking { store.manifest.first() } ?: return
        val prefs = appContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val nowMs = System.currentTimeMillis()

        for (clip in manifest.clips) {
            if (clip.trigger.kind != "biometric_threshold") continue
            if (!shouldFire(clip, reading)) continue
            val lastFired = prefs.getLong(clip.id, 0L)
            if (nowMs - lastFired < DEFAULT_COOLDOWN_MS) continue
            enqueuePlayback(manifest.capsule_id, clip)
            prefs.edit().putLong(clip.id, nowMs).apply()
        }
    }

    private fun shouldFire(clip: CapsuleClip, reading: MobileBiometrics): Boolean {
        val metric = clip.trigger.metric ?: return false
        val op = clip.trigger.op ?: return false
        val threshold = clip.trigger.value ?: return false
        val sample = metricValue(reading, metric) ?: return false
        return when (op) {
            "gt" -> sample > threshold
            "lt" -> sample < threshold
            else -> false
        }
    }

    private fun metricValue(reading: MobileBiometrics, metric: String): Double? {
        return when (metric) {
            "heart_rate" -> reading.heart_rate?.toDouble()
            "spo2" -> reading.spo2?.toDouble()
            "steps" -> reading.steps?.toDouble()
            "stress" -> reading.stress_level?.toDouble()
            "sleep_duration_minutes" -> reading.sleep_duration_minutes?.toDouble()
            // "fatigue" is computed server-side; the phone receives it later.
            else -> null
        }
    }

    private fun enqueuePlayback(capsuleId: String, clip: CapsuleClip) {
        val data = Data.Builder()
            .putString(CapsulePlaybackWorker.KEY_CAPSULE_ID, capsuleId)
            .putString(CapsulePlaybackWorker.KEY_CLIP_ID, clip.id)
            .putString(CapsulePlaybackWorker.KEY_AUDIO_URL, clip.audio_url)
            .putLong(CapsulePlaybackWorker.KEY_SCHEDULED_AT_MS, System.currentTimeMillis())
            .build()
        val request = OneTimeWorkRequestBuilder<CapsulePlaybackWorker>()
            .setInputData(data)
            .addTag(CapsulePlaybackWorker.TAG)
            .build()
        WorkManager.getInstance(appContext).enqueue(request)
    }

    companion object {
        private const val PREFS = "hems.biometric_cooldown"
        // Fixed 30-minute cooldown — per-clip cooldown_min isn't meaningful here
        // because biometric events stream; the user doesn't want redundant prompts.
        private const val DEFAULT_COOLDOWN_MS = 30L * 60 * 1000L
    }
}
