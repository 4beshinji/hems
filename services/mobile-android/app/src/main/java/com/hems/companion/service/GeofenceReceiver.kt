package com.hems.companion.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import androidx.work.Data
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingEvent
import com.hems.companion.data.api.CapsuleManifest
import com.hems.companion.data.preferences.CapsuleStore
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking

/**
 * Receives [Geofence] transitions for capsule clips. Matches the triggered
 * clip by its geofence request id and enqueues the same
 * [CapsulePlaybackWorker] used by AlarmManager.
 *
 * Runtime cooldown is enforced here via SharedPreferences — the manifest
 * carries ``cooldown_min`` per clip (from FrequentPlace.cooldown_min).
 */
@AndroidEntryPoint
class GeofenceReceiver : BroadcastReceiver() {

    @Inject lateinit var store: CapsuleStore

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION) return
        val event = GeofencingEvent.fromIntent(intent) ?: return
        if (event.hasError()) return
        val transition = event.geofenceTransition
        if (transition != Geofence.GEOFENCE_TRANSITION_ENTER) return

        val manifest = runBlocking { store.manifest.first() } ?: return
        val cooldownPrefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

        for (fence in event.triggeringGeofences.orEmpty()) {
            val clip = manifest.clips.firstOrNull { it.id == fence.requestId } ?: continue
            if (!withinCooldown(cooldownPrefs, clip.id, clip.trigger.cooldown_min)) {
                continue
            }
            enqueuePlayback(context, manifest, clip)
            markFired(cooldownPrefs, clip.id)
        }
    }

    private fun withinCooldown(
        prefs: SharedPreferences,
        clipId: String,
        cooldownMin: Int?,
    ): Boolean {
        val cooldownMs = ((cooldownMin ?: 60).coerceAtLeast(1)).toLong() * 60_000L
        val last = prefs.getLong(clipId, 0L)
        val now = System.currentTimeMillis()
        return (now - last) >= cooldownMs
    }

    private fun markFired(prefs: SharedPreferences, clipId: String) {
        prefs.edit().putLong(clipId, System.currentTimeMillis()).apply()
    }

    private fun enqueuePlayback(
        context: Context,
        manifest: CapsuleManifest,
        clip: com.hems.companion.data.api.CapsuleClip,
    ) {
        val data = Data.Builder()
            .putString(CapsulePlaybackWorker.KEY_CAPSULE_ID, manifest.capsule_id)
            .putString(CapsulePlaybackWorker.KEY_CLIP_ID, clip.id)
            .putString(CapsulePlaybackWorker.KEY_AUDIO_URL, clip.audio_url)
            .putLong(CapsulePlaybackWorker.KEY_SCHEDULED_AT_MS, System.currentTimeMillis())
            .build()
        val request = OneTimeWorkRequestBuilder<CapsulePlaybackWorker>()
            .setInputData(data)
            .addTag(CapsulePlaybackWorker.TAG)
            .build()
        WorkManager.getInstance(context).enqueue(request)
    }

    companion object {
        const val ACTION = "com.hems.companion.GEOFENCE_TRIGGER"
        const val EXTRA_CAPSULE_ID = "capsule_id"
        private const val PREFS = "hems.geofence_cooldown"
    }
}
