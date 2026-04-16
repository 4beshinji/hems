package com.hems.companion.service

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import dagger.hilt.android.qualifiers.ApplicationContext
import java.time.Duration
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SyncScheduler @Inject constructor(
    @ApplicationContext private val appContext: Context,
) {

    /**
     * Enqueue (or replace) the periodic sensor-batch worker.
     *
     * WorkManager enforces a 15-minute minimum for periodic requests — the
     * plan calls for ~5 min but that requires OneTime+delay chaining and is
     * deferred to a later phase.
     */
    fun enqueuePeriodicBatch() {
        val request = PeriodicWorkRequestBuilder<SensorBatchWorker>(Duration.ofMinutes(15))
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build()
            )
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, Duration.ofMinutes(1))
            .addTag(SensorBatchWorker.TAG)
            .build()
        WorkManager.getInstance(appContext).enqueueUniquePeriodicWork(
            SensorBatchWorker.UNIQUE_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    fun cancelPeriodicBatch() {
        WorkManager.getInstance(appContext).cancelUniqueWork(SensorBatchWorker.UNIQUE_NAME)
    }

    /**
     * Enqueue a daily capsule download. WorkManager's minimum period is 15
     * minutes; the morning window is the main target so any firing in a
     * 24-hour cycle is fine — CapsuleDownloadWorker is idempotent.
     */
    fun enqueueCapsuleDownload() {
        val request = PeriodicWorkRequestBuilder<CapsuleDownloadWorker>(Duration.ofHours(6))
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build()
            )
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, Duration.ofMinutes(5))
            .addTag(CapsuleDownloadWorker.TAG)
            .build()
        WorkManager.getInstance(appContext).enqueueUniquePeriodicWork(
            CapsuleDownloadWorker.UNIQUE_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }
}
