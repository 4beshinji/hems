package com.hems.healthconnect

import android.content.Context
import android.util.Log
import androidx.work.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

/**
 * WorkManager periodic worker that reads Health Connect data
 * and posts it to the HEMS biometric-bridge webhook.
 *
 * Runs every N minutes (configured in SettingsRepository).
 * Android 15+ supports READ_HEALTH_DATA_IN_BACKGROUND for true background reads.
 */
class DataSyncWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "DataSyncWorker"
        private const val WORK_NAME = "hems_health_sync"

        fun schedule(context: Context, intervalMinutes: Int) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val request = PeriodicWorkRequestBuilder<DataSyncWorker>(
                intervalMinutes.toLong(), TimeUnit.MINUTES,
            )
                .setConstraints(constraints)
                .setBackoffCriteria(
                    BackoffPolicy.EXPONENTIAL,
                    WorkRequest.MIN_BACKOFF_MILLIS,
                    TimeUnit.MILLISECONDS,
                )
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.UPDATE,
                request,
            )

            Log.i(TAG, "Scheduled sync every ${intervalMinutes}min")
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
        }
    }

    override suspend fun doWork(): Result {
        val settings = SettingsRepository(applicationContext)
        if (!settings.isConfigured) {
            Log.w(TAG, "Bridge URL not configured, skipping")
            return Result.failure()
        }

        val reader = HealthConnectReader(applicationContext)

        // Check permissions
        if (!reader.hasPermissions()) {
            Log.w(TAG, "Health Connect permissions not granted, skipping")
            settings.lastSyncStatus = "error: permissions not granted"
            return Result.failure()
        }

        return withContext(Dispatchers.IO) {
            try {
                val data = reader.readLatest()
                val client = HemsBridgeClient(settings.bridgeUrl, settings.webhookSecret)
                val success = client.postReading(data)

                if (success) {
                    settings.lastSyncTimestamp = System.currentTimeMillis()
                    settings.lastSyncStatus = "success"
                    Log.i(TAG, "Sync complete: ${data.length()} fields")
                    Result.success()
                } else {
                    settings.lastSyncStatus = "error: bridge returned error"
                    Log.e(TAG, "Bridge rejected data")
                    Result.retry()
                }
            } catch (e: Exception) {
                settings.lastSyncStatus = "error: ${e.message}"
                Log.e(TAG, "Sync failed", e)
                Result.retry()
            }
        }
    }
}
