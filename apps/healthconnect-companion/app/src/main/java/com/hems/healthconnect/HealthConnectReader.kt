package com.hems.healthconnect

import android.content.Context
import android.util.Log
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.*
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import org.json.JSONObject
import java.time.Instant
import java.time.temporal.ChronoUnit

/**
 * Reads biometric data from Health Connect (fed by Mi Fitness app).
 * Data types: HeartRate, SpO2, Sleep, Steps, Calories, RestingHeartRate, HRV.
 */
class HealthConnectReader(private val context: Context) {

    private val client: HealthConnectClient by lazy {
        HealthConnectClient.getOrCreate(context)
    }

    companion object {
        private const val TAG = "HealthConnectReader"

        val REQUIRED_PERMISSIONS = setOf(
            HealthPermission.getReadPermission(HeartRateRecord::class),
            HealthPermission.getReadPermission(OxygenSaturationRecord::class),
            HealthPermission.getReadPermission(SleepSessionRecord::class),
            HealthPermission.getReadPermission(StepsRecord::class),
            HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class),
            HealthPermission.getReadPermission(RestingHeartRateRecord::class),
            HealthPermission.getReadPermission(HeartRateVariabilityRmssdRecord::class),
        )
    }

    suspend fun hasPermissions(): Boolean {
        val granted = client.permissionController.getGrantedPermissions()
        return granted.containsAll(REQUIRED_PERMISSIONS)
    }

    /**
     * Read recent biometric data and return as a flat JSON payload
     * compatible with the HEMS biometric-bridge webhook format.
     */
    suspend fun readLatest(): JSONObject {
        val now = Instant.now()
        val since = now.minus(30, ChronoUnit.MINUTES)
        val sinceSleep = now.minus(24, ChronoUnit.HOURS)

        val payload = JSONObject().apply {
            put("provider", "healthconnect")
            put("timestamp", now.epochSecond.toDouble())
        }

        // Heart Rate — latest sample
        try {
            val hrRecords = client.readRecords(
                ReadRecordsRequest(
                    recordType = HeartRateRecord::class,
                    timeRangeFilter = TimeRangeFilter.after(since),
                )
            ).records
            if (hrRecords.isNotEmpty()) {
                val latest = hrRecords.last()
                val lastSample = latest.samples.lastOrNull()
                if (lastSample != null) {
                    payload.put("heart_rate", lastSample.beatsPerMinute)
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read HR: ${e.message}")
        }

        // Resting Heart Rate
        try {
            val rhrRecords = client.readRecords(
                ReadRecordsRequest(
                    recordType = RestingHeartRateRecord::class,
                    timeRangeFilter = TimeRangeFilter.after(since),
                )
            ).records
            if (rhrRecords.isNotEmpty()) {
                payload.put("resting_heart_rate", rhrRecords.last().beatsPerMinute)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read resting HR: ${e.message}")
        }

        // SpO2
        try {
            val spo2Records = client.readRecords(
                ReadRecordsRequest(
                    recordType = OxygenSaturationRecord::class,
                    timeRangeFilter = TimeRangeFilter.after(since),
                )
            ).records
            if (spo2Records.isNotEmpty()) {
                payload.put("spo2", spo2Records.last().percentage.value.toInt())
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read SpO2: ${e.message}")
        }

        // Steps — aggregate today
        try {
            val todayStart = now.truncatedTo(ChronoUnit.DAYS)
            val stepRecords = client.readRecords(
                ReadRecordsRequest(
                    recordType = StepsRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(todayStart, now),
                )
            ).records
            if (stepRecords.isNotEmpty()) {
                val totalSteps = stepRecords.sumOf { it.count }
                payload.put("steps", totalSteps)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read steps: ${e.message}")
        }

        // Calories — aggregate today
        try {
            val todayStart = now.truncatedTo(ChronoUnit.DAYS)
            val calRecords = client.readRecords(
                ReadRecordsRequest(
                    recordType = ActiveCaloriesBurnedRecord::class,
                    timeRangeFilter = TimeRangeFilter.between(todayStart, now),
                )
            ).records
            if (calRecords.isNotEmpty()) {
                val totalCal = calRecords.sumOf { it.energy.inKilocalories }
                payload.put("calories", totalCal.toInt())
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read calories: ${e.message}")
        }

        // HRV (RMSSD)
        try {
            val hrvRecords = client.readRecords(
                ReadRecordsRequest(
                    recordType = HeartRateVariabilityRmssdRecord::class,
                    timeRangeFilter = TimeRangeFilter.after(since),
                )
            ).records
            if (hrvRecords.isNotEmpty()) {
                payload.put("hrv", hrvRecords.last().heartRateVariabilityMillis.toInt())
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read HRV: ${e.message}")
        }

        // Sleep — last session within 24h
        try {
            val sleepRecords = client.readRecords(
                ReadRecordsRequest(
                    recordType = SleepSessionRecord::class,
                    timeRangeFilter = TimeRangeFilter.after(sinceSleep),
                )
            ).records
            if (sleepRecords.isNotEmpty()) {
                val session = sleepRecords.last()
                val durationMin = ChronoUnit.MINUTES.between(session.startTime, session.endTime)
                payload.put("sleep_duration", durationMin)
                payload.put("sleep_start_ts", session.startTime.epochSecond.toDouble())
                payload.put("sleep_end_ts", session.endTime.epochSecond.toDouble())

                // Parse sleep stages
                var deepMin = 0L
                var remMin = 0L
                var lightMin = 0L
                for (stage in session.stages) {
                    val stageMin = ChronoUnit.MINUTES.between(stage.startTime, stage.endTime)
                    when (stage.stage) {
                        SleepSessionRecord.STAGE_TYPE_DEEP -> deepMin += stageMin
                        SleepSessionRecord.STAGE_TYPE_REM -> remMin += stageMin
                        SleepSessionRecord.STAGE_TYPE_LIGHT -> lightMin += stageMin
                    }
                }
                if (deepMin > 0) payload.put("sleep_deep", deepMin)
                if (remMin > 0) payload.put("sleep_rem", remMin)
                if (lightMin > 0) payload.put("sleep_light", lightMin)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read sleep: ${e.message}")
        }

        return payload
    }
}
