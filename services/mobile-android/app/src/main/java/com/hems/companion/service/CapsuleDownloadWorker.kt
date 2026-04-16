package com.hems.companion.service

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.hems.companion.data.repository.CapsuleRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject

/**
 * Downloads the latest voice capsule (manifest + every clip MP3) and, on
 * success, hands the manifest to [CapsuleAlarmScheduler] so AlarmManager
 * wakes for each time-triggered clip.
 */
@HiltWorker
class CapsuleDownloadWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val repo: CapsuleRepository,
    private val scheduler: CapsuleAlarmScheduler,
    private val geofenceRegistrar: GeofenceRegistrar,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        return repo.fetchAndDownload().fold(
            onSuccess = { manifest ->
                scheduler.scheduleAll(manifest)
                geofenceRegistrar.clear(previousCapsuleId = manifest.capsule_id)
                geofenceRegistrar.register(manifest)
                Result.success()
            },
            onFailure = { err ->
                if (err is IllegalStateException) Result.success() // not registered yet
                else Result.retry()
            },
        )
    }

    companion object {
        const val UNIQUE_NAME = "hems.capsule_download"
        const val TAG = "capsule-download"
    }
}
