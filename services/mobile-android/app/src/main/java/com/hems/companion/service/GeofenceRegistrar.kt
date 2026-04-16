package com.hems.companion.service

import android.Manifest
import android.annotation.SuppressLint
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import com.google.android.gms.location.Geofence
import com.google.android.gms.location.GeofencingClient
import com.google.android.gms.location.GeofencingRequest
import com.google.android.gms.location.LocationServices
import com.hems.companion.data.api.CapsuleClip
import com.hems.companion.data.api.CapsuleManifest
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Registers ``Geofence`` objects for every ``geofence`` clip in a manifest.
 * Fired geofences hit [GeofenceReceiver], which enqueues the usual
 * [CapsulePlaybackWorker] (same playback path as AlarmManager triggers).
 *
 * Requires ACCESS_FINE_LOCATION + ACCESS_BACKGROUND_LOCATION at runtime;
 * if either is missing we silently skip registration — the manifest's other
 * triggers (time / pre_event) remain functional.
 */
@Singleton
class GeofenceRegistrar @Inject constructor(
    @ApplicationContext private val appContext: Context,
) {
    private val client: GeofencingClient = LocationServices.getGeofencingClient(appContext)

    @SuppressLint("MissingPermission")
    fun register(manifest: CapsuleManifest) {
        if (!hasLocationPermissions()) return
        val requests = manifest.clips
            .filter { it.trigger.kind == "geofence" }
            .mapNotNull { it.toGeofence() }
        if (requests.isEmpty()) return

        val fenceRequest = GeofencingRequest.Builder()
            .setInitialTrigger(GeofencingRequest.INITIAL_TRIGGER_ENTER)
            .addGeofences(requests)
            .build()
        client.addGeofences(fenceRequest, pendingIntent(manifest))
    }

    /**
     * Remove all registered geofences. Called before a new [register] run
     * to avoid stale fences from a prior manifest.
     */
    fun clear(previousCapsuleId: String? = null) {
        client.removeGeofences(pendingIntent(previousCapsuleId))
    }

    private fun CapsuleClip.toGeofence(): Geofence? {
        val lat = trigger.lat ?: return null
        val lon = trigger.lon ?: return null
        val radius = (trigger.radius_m ?: 200).toFloat()
        return Geofence.Builder()
            .setRequestId(id)  // clip.id is globally unique per manifest
            .setCircularRegion(lat, lon, radius)
            .setExpirationDuration(Geofence.NEVER_EXPIRE)
            .setTransitionTypes(Geofence.GEOFENCE_TRANSITION_ENTER)
            .build()
    }

    private fun hasLocationPermissions(): Boolean {
        fun granted(name: String) = ContextCompat.checkSelfPermission(appContext, name) ==
            PackageManager.PERMISSION_GRANTED
        return granted(Manifest.permission.ACCESS_FINE_LOCATION) &&
            granted(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
    }

    private fun pendingIntent(manifest: CapsuleManifest): PendingIntent =
        pendingIntent(manifest.capsule_id)

    private fun pendingIntent(capsuleId: String?): PendingIntent {
        val intent = Intent(appContext, GeofenceReceiver::class.java)
            .setAction(GeofenceReceiver.ACTION)
            .putExtra(GeofenceReceiver.EXTRA_CAPSULE_ID, capsuleId ?: "")
        return PendingIntent.getBroadcast(
            appContext,
            REQUEST_CODE,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
        )
    }

    companion object {
        private const val REQUEST_CODE = 42
    }
}
