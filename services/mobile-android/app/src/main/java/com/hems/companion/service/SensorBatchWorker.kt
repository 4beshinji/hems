package com.hems.companion.service

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.hems.companion.data.repository.SyncRepository
import com.hems.companion.domain.sync.SensorBuffer
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject

/**
 * Drains the newest sample from [SensorBuffer] and submits it to the
 * backend. Runs periodically via WorkManager (min interval 15min due to
 * platform constraints) and ad-hoc whenever the FGS wants an immediate flush.
 */
@HiltWorker
class SensorBatchWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val buffer: SensorBuffer,
    private val repo: SyncRepository,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val payload = buffer.drainLatest() ?: return Result.success()
        return when (val outcome = repo.submit(payload)) {
            SyncRepository.Outcome.Ok -> Result.success()
            SyncRepository.Outcome.NotRegistered -> Result.success()
            is SyncRepository.Outcome.Http ->
                if (outcome.code in 500..599) Result.retry() else Result.failure()
            is SyncRepository.Outcome.Network -> Result.retry()
        }
    }

    companion object {
        const val UNIQUE_NAME = "hems.sensor_batch"
        const val TAG = "sensor-batch"
    }
}
