package com.hems.healthconnect

import android.content.Context
import android.util.Log
import androidx.work.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * WorkManager periodic worker that reads Health Connect data
 * and posts it to the HEMS biometric-bridge webhook.
 *
 * Offline-resilient: readings are always saved to Room DB first,
 * then flushed to the bridge. If the bridge is unreachable,
 * data accumulates locally and is sent on next successful sync.
 */
class DataSyncWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "DataSyncWorker"
        private const val WORK_NAME = "hems_health_sync"
        private const val MAX_AGE_MS = 24 * 60 * 60 * 1000L // 24h

        fun schedule(context: Context, intervalMinutes: Int) {
            // No network constraint — we still want to read Health Connect
            // and queue data locally even when offline
            val request = PeriodicWorkRequestBuilder<DataSyncWorker>(
                intervalMinutes.toLong(), TimeUnit.MINUTES,
            )
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

        if (!reader.hasPermissions()) {
            Log.w(TAG, "Health Connect permissions not granted, skipping")
            settings.lastSyncStatus = "error: permissions not granted"
            return Result.failure()
        }

        val dao = HemsDatabase.getInstance(applicationContext).pendingReadingDao()

        return withContext(Dispatchers.IO) {
            try {
                // 1. Read Health Connect data and always save to local queue first
                val data = reader.readLatest()
                dao.insert(PendingReadingEntity(payloadJson = data.toString()))
                Log.d(TAG, "Reading queued locally (${data.length()} fields)")

                // 2. Prune old entries (>24h)
                dao.pruneOlderThan(System.currentTimeMillis() - MAX_AGE_MS)

                // 3. Try to flush all pending readings to the bridge
                val client = HemsBridgeClient(settings.bridgeUrl, settings.webhookSecret)
                val pending = dao.getOldest(50)
                val sent = mutableListOf<PendingReadingEntity>()

                for (entity in pending) {
                    try {
                        val payload = JSONObject(entity.payloadJson)
                        if (client.postReading(payload)) {
                            sent.add(entity)
                        } else {
                            // Bridge returned error — stop flushing, retry later
                            break
                        }
                    } catch (e: Exception) {
                        // Network error — stop flushing, data stays in queue
                        Log.w(TAG, "Flush stopped: ${e.message}")
                        break
                    }
                }

                if (sent.isNotEmpty()) {
                    dao.delete(sent)
                }

                val remaining = dao.pendingCount()
                settings.lastSyncTimestamp = System.currentTimeMillis()
                settings.lastSyncStatus = if (remaining == 0) {
                    "success"
                } else {
                    "partial: $remaining pending"
                }
                Log.i(TAG, "Sync: ${sent.size} sent, $remaining pending")
                Result.success()
            } catch (e: Exception) {
                settings.lastSyncStatus = "error: ${e.message}"
                Log.e(TAG, "Sync failed", e)
                // Return success — data is safely queued, no need to retry immediately
                Result.success()
            }
        }
    }
}
