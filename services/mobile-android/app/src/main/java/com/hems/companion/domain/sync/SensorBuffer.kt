package com.hems.companion.domain.sync

import com.hems.companion.data.api.MobileActivity
import com.hems.companion.data.api.MobileBiometrics
import com.hems.companion.data.api.MobileLocation
import com.hems.companion.data.api.MobileStatePayload
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.concurrent.ConcurrentLinkedDeque
import javax.inject.Inject
import javax.inject.Singleton

/**
 * In-memory buffer of pending sensor observations. The foreground service
 * appends on each callback; the WorkManager job drains at ~5 min cadence
 * and hands the batch to [com.hems.companion.data.repository.SyncRepository].
 *
 * Bounded at [MAX_ENTRIES] per kind — oldest is evicted on overflow so the
 * phone never grows this heap without bound when offline or VPN-down.
 */
@Singleton
class SensorBuffer @Inject constructor() {
    private val locations = ConcurrentLinkedDeque<TimedLocation>()
    private val activities = ConcurrentLinkedDeque<TimedActivity>()
    private val biometrics = ConcurrentLinkedDeque<TimedBiometrics>()

    @Volatile private var batteryPct: Int? = null

    fun recordLocation(reading: MobileLocation, at: Instant = Instant.now()) {
        locations.add(TimedLocation(at, reading))
        trim(locations)
    }

    fun recordActivity(reading: MobileActivity, at: Instant = Instant.now()) {
        activities.add(TimedActivity(at, reading))
        trim(activities)
    }

    fun recordBiometrics(reading: MobileBiometrics, at: Instant = Instant.now()) {
        biometrics.add(TimedBiometrics(at, reading))
        trim(biometrics)
    }

    fun recordBattery(percent: Int) {
        batteryPct = percent.coerceIn(0, 100)
    }

    /** Drain the newest sample from each queue into a single batched payload. */
    fun drainLatest(): MobileStatePayload? {
        val loc = locations.pollLast()
        val act = activities.pollLast()
        val bio = biometrics.pollLast()
        val batt = batteryPct.also { batteryPct = null }

        // If nothing to report, let the caller skip the HTTP.
        if (loc == null && act == null && bio == null && batt == null) return null

        // Pick the most recent timestamp among observations; fall back to now.
        val ts = listOfNotNull(loc?.at, act?.at, bio?.at).maxOrNull() ?: Instant.now()
        return MobileStatePayload(
            ts = FORMATTER.format(ts),
            location = loc?.reading,
            activity = act?.reading,
            biometrics = bio?.reading,
            battery_pct = batt,
        )
    }

    /** Clear everything. Used on logout / credential reset. */
    fun clear() {
        locations.clear()
        activities.clear()
        biometrics.clear()
        batteryPct = null
    }

    private fun <T> trim(deque: ConcurrentLinkedDeque<T>) {
        while (deque.size > MAX_ENTRIES) deque.pollFirst()
    }

    private data class TimedLocation(val at: Instant, val reading: MobileLocation)
    private data class TimedActivity(val at: Instant, val reading: MobileActivity)
    private data class TimedBiometrics(val at: Instant, val reading: MobileBiometrics)

    companion object {
        private const val MAX_ENTRIES = 256
        private val FORMATTER: DateTimeFormatter =
            DateTimeFormatter.ISO_OFFSET_DATE_TIME.withZone(ZoneId.systemDefault())
    }
}
