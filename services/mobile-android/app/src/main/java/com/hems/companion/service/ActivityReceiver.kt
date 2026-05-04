package com.hems.companion.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.google.android.gms.location.ActivityRecognitionResult
import com.google.android.gms.location.DetectedActivity
import com.hems.companion.data.api.MobileActivity
import com.hems.companion.domain.sync.SensorBuffer
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/**
 * Receives activity-recognition broadcasts and forwards the most likely
 * activity to the [SensorBuffer]. The PendingIntent that targets this
 * receiver is registered by [SyncForegroundService] at service start.
 */
@AndroidEntryPoint
class ActivityReceiver : BroadcastReceiver() {

    @Inject lateinit var buffer: SensorBuffer

    override fun onReceive(context: Context, intent: Intent) {
        if (!ActivityRecognitionResult.hasResult(intent)) return
        val result = ActivityRecognitionResult.extractResult(intent) ?: return
        val top = result.mostProbableActivity ?: return
        buffer.recordActivity(
            MobileActivity(
                kind = kindOf(top.type),
                confidence = top.confidence,
            )
        )
    }

    private fun kindOf(type: Int): String = when (type) {
        DetectedActivity.STILL -> "still"
        DetectedActivity.WALKING, DetectedActivity.ON_FOOT -> "walking"
        DetectedActivity.RUNNING -> "running"
        DetectedActivity.IN_VEHICLE -> "in_vehicle"
        DetectedActivity.ON_BICYCLE -> "on_bicycle"
        else -> "unknown"
    }

    companion object {
        const val ACTION = "com.hems.companion.ACTIVITY_UPDATE"
    }
}
