package com.hems.companion.service

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.location.Location
import android.os.Build
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.google.android.gms.location.ActivityRecognition
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.hems.companion.MainActivity
import com.hems.companion.R
import com.hems.companion.data.api.MobileLocation
import com.hems.companion.domain.sync.SensorBuffer
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/**
 * Persistent foreground service that streams sensor readings into the
 * in-memory [SensorBuffer]. The service is backed by a FOREGROUND_SERVICE
 * of type `location` — required for background FusedLocation access on
 * Android 10+.
 *
 * Responsibilities:
 *  - Keep a notification ongoing so the OS lets us observe location.
 *  - Register FusedLocationProvider updates (~5 min) and forward to buffer.
 *  - Register ActivityRecognition updates via PendingIntent → [ActivityReceiver].
 *  - Enqueue the periodic [SensorBatchWorker] via [SyncScheduler].
 */
@AndroidEntryPoint
class SyncForegroundService : Service() {

    @Inject lateinit var buffer: SensorBuffer
    @Inject lateinit var scheduler: SyncScheduler

    private lateinit var fused: FusedLocationProviderClient
    private val locationCallback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            val last: Location = result.lastLocation ?: return
            buffer.recordLocation(
                MobileLocation(
                    lat = last.latitude,
                    lon = last.longitude,
                    accuracy_m = if (last.hasAccuracy()) last.accuracy.toDouble() else null,
                    speed_mps = if (last.hasSpeed()) last.speed.toDouble() else null,
                    heading_deg = if (last.hasBearing()) last.bearing.toDouble() else null,
                    provider = "fused",
                )
            )
        }
    }

    override fun onCreate() {
        super.onCreate()
        fused = LocationServices.getFusedLocationProviderClient(this)
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startInForeground()
        if (!hasLocationPermission()) {
            stopSelf()
            return START_NOT_STICKY
        }
        requestLocationUpdates()
        requestActivityUpdates()
        scheduler.enqueuePeriodicBatch()
        scheduler.enqueueCapsuleDownload()
        return START_STICKY
    }

    override fun onDestroy() {
        try {
            fused.removeLocationUpdates(locationCallback)
            ActivityRecognition.getClient(this).removeActivityUpdates(activityPendingIntent())
        } catch (_: SecurityException) { /* permission may have been revoked */ }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ------------------------------------------------------------------------

    private fun hasLocationPermission(): Boolean {
        val fine = ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        val coarse = ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_COARSE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        return fine || coarse
    }

    @Suppress("MissingPermission")
    private fun requestLocationUpdates() {
        val request = LocationRequest.Builder(LOCATION_INTERVAL_MS)
            .setMinUpdateIntervalMillis(LOCATION_MIN_INTERVAL_MS)
            .setPriority(Priority.PRIORITY_BALANCED_POWER_ACCURACY)
            .build()
        fused.requestLocationUpdates(request, locationCallback, Looper.getMainLooper())
    }

    @Suppress("MissingPermission")
    private fun requestActivityUpdates() {
        ActivityRecognition.getClient(this)
            .requestActivityUpdates(ACTIVITY_INTERVAL_MS, activityPendingIntent())
    }

    private fun activityPendingIntent(): PendingIntent {
        val intent = Intent(this, ActivityReceiver::class.java).setAction(ActivityReceiver.ACTION)
        return PendingIntent.getBroadcast(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
        )
    }

    private fun startInForeground() {
        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun buildNotification(): Notification {
        val openApp = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.app_name))
            .setContentText("HEMS: センサー同期中")
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentIntent(openApp)
            .setOngoing(true)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val mgr = getSystemService(NotificationManager::class.java) ?: return
        if (mgr.getNotificationChannel(CHANNEL_ID) != null) return
        val channel = NotificationChannel(
            CHANNEL_ID, "HEMS 同期", NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "センサー同期が動作中であることを示す通知"
        }
        mgr.createNotificationChannel(channel)
    }

    companion object {
        private const val CHANNEL_ID = "hems_sync"
        private const val NOTIFICATION_ID = 1001
        private const val LOCATION_INTERVAL_MS = 5 * 60 * 1000L
        private const val LOCATION_MIN_INTERVAL_MS = 60 * 1000L
        private const val ACTIVITY_INTERVAL_MS = 5 * 60 * 1000L
    }
}
