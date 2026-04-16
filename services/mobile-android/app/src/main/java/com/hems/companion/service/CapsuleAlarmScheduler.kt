package com.hems.companion.service

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import com.hems.companion.data.api.CapsuleManifest
import com.hems.companion.data.preferences.CapsuleStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.runBlocking

/**
 * Programs AlarmManager alarms for every time-triggered clip in a manifest.
 *
 * Time-based triggers (``time`` + ``pre_event``) each get an exact alarm.
 * Geofence triggers are owned by [GeofenceRegistrar]; biometric-threshold
 * is a P5 concern and is silently skipped.
 *
 * Prior clip ids are persisted to [CapsuleStore] so [cancelAll] can cancel
 * the previous round's PendingIntents — otherwise removed clips would
 * continue firing until their alarm RTC wakes the phone.
 */
@Singleton
class CapsuleAlarmScheduler @Inject constructor(
    @ApplicationContext private val appContext: Context,
    private val store: CapsuleStore,
) {

    private val alarmManager =
        appContext.getSystemService(AlarmManager::class.java)
            ?: error("AlarmManager unavailable")

    fun scheduleAll(manifest: CapsuleManifest) {
        runBlocking { cancelAll() }
        val newIds = mutableSetOf<String>()
        for (clip in manifest.clips) {
            if (clip.trigger.kind !in ACCEPTED_TIME_KINDS) continue
            val ts = clip.trigger.absolute_ts ?: continue
            val triggerAtMillis = ts * 1000L
            if (triggerAtMillis <= System.currentTimeMillis()) continue
            val intent = makeIntent(manifest.capsule_id, clip.id, clip.audio_url)
            val pi = PendingIntent.getBroadcast(
                appContext,
                pendingIntentRequestCode(clip.id),
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            setAlarm(triggerAtMillis, pi)
            newIds += clip.id
        }
        runBlocking { store.setScheduledClipIds(newIds) }
    }

    /** Cancel every alarm from the prior manifest. Safe to call with no prior state. */
    suspend fun cancelAll() {
        val priorIds = store.scheduledClipIds()
        if (priorIds.isEmpty()) return
        for (id in priorIds) {
            val pi = PendingIntent.getBroadcast(
                appContext,
                pendingIntentRequestCode(id),
                Intent(appContext, CapsulePlaybackReceiver::class.java)
                    .setAction(CapsulePlaybackReceiver.ACTION_PLAY),
                PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE,
            ) ?: continue
            alarmManager.cancel(pi)
            pi.cancel()
        }
        store.setScheduledClipIds(emptySet())
    }

    private fun pendingIntentRequestCode(clipId: String): Int = clipId.hashCode()

    private fun makeIntent(capsuleId: String, clipId: String, audioUrl: String): Intent =
        Intent(appContext, CapsulePlaybackReceiver::class.java)
            .setAction(CapsulePlaybackReceiver.ACTION_PLAY)
            .putExtra(CapsulePlaybackReceiver.EXTRA_CAPSULE_ID, capsuleId)
            .putExtra(CapsulePlaybackReceiver.EXTRA_CLIP_ID, clipId)
            .putExtra(CapsulePlaybackReceiver.EXTRA_AUDIO_URL, audioUrl)

    private fun setAlarm(triggerAtMillis: Long, pi: PendingIntent) {
        val canExact = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
            alarmManager.canScheduleExactAlarms() else true
        if (canExact) {
            alarmManager.setExactAndAllowWhileIdle(
                AlarmManager.RTC_WAKEUP, triggerAtMillis, pi,
            )
        } else {
            alarmManager.setAndAllowWhileIdle(
                AlarmManager.RTC_WAKEUP, triggerAtMillis, pi,
            )
        }
    }

    companion object {
        private val ACCEPTED_TIME_KINDS = setOf("time", "pre_event")
    }
}
