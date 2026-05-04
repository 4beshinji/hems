package com.hems.companion.service

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.hems.companion.data.api.MobileBiometrics
import com.hems.companion.domain.sync.SensorBuffer
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.time.Duration
import java.time.Instant

/**
 * Reads recent heart-rate, steps and sleep from Health Connect, pushes them
 * to [SensorBuffer] (for the next webhook batch) and to
 * [BiometricEvaluator] (for threshold-triggered capsule playback).
 *
 * Scheduled alongside [SensorBatchWorker] — both fire every 15 min.
 */
@HiltWorker
class HealthConnectWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val buffer: SensorBuffer,
    private val evaluator: BiometricEvaluator,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val available = try {
            HealthConnectClient.getSdkStatus(applicationContext) ==
                HealthConnectClient.SDK_AVAILABLE
        } catch (_: Exception) { false }
        if (!available) return Result.success()

        val client = HealthConnectClient.getOrCreate(applicationContext)
        val granted = client.permissionController.getGrantedPermissions()
        if (granted.isEmpty()) return Result.success()

        val now = Instant.now()
        val since = now.minus(LOOKBACK)
        val reading = MobileBiometrics(
            heart_rate = readLatestHeartRate(client, since, now, granted),
            steps = readSteps(client, since, now, granted),
            sleep_duration_minutes = readSleepMinutes(client, since, now, granted),
        )

        if (reading.heart_rate != null || reading.steps != null || reading.sleep_duration_minutes != null) {
            buffer.recordBiometrics(reading)
            evaluator.onBiometrics(reading)
        }
        return Result.success()
    }

    private suspend fun readLatestHeartRate(
        client: HealthConnectClient, since: Instant, until: Instant,
        granted: Set<String>,
    ): Int? {
        if (HealthPermission.getReadPermission(HeartRateRecord::class) !in granted) return null
        return runCatching {
            val resp = client.readRecords(
                ReadRecordsRequest(
                    HeartRateRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(since, until),
                )
            )
            resp.records.lastOrNull()?.samples?.lastOrNull()?.beatsPerMinute?.toInt()
        }.getOrNull()
    }

    private suspend fun readSteps(
        client: HealthConnectClient, since: Instant, until: Instant,
        granted: Set<String>,
    ): Int? {
        if (HealthPermission.getReadPermission(StepsRecord::class) !in granted) return null
        return runCatching {
            val resp = client.readRecords(
                ReadRecordsRequest(
                    StepsRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(since, until),
                )
            )
            resp.records.sumOf { it.count }.toInt().takeIf { it > 0 }
        }.getOrNull()
    }

    private suspend fun readSleepMinutes(
        client: HealthConnectClient, since: Instant, until: Instant,
        granted: Set<String>,
    ): Int? {
        if (HealthPermission.getReadPermission(SleepSessionRecord::class) !in granted) return null
        return runCatching {
            val resp = client.readRecords(
                ReadRecordsRequest(
                    SleepSessionRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(since, until),
                )
            )
            resp.records.lastOrNull()?.let {
                Duration.between(it.startTime, it.endTime).toMinutes().toInt()
            }
        }.getOrNull()
    }

    companion object {
        const val UNIQUE_NAME = "hems.health_connect"
        const val TAG = "health-connect"
        private val LOOKBACK = Duration.ofMinutes(20)
    }
}
