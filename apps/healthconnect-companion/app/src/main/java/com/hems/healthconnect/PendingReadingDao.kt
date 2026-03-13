package com.hems.healthconnect

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query

@Dao
interface PendingReadingDao {
    @Insert
    suspend fun insert(reading: PendingReadingEntity)

    @Query("SELECT * FROM pending_readings ORDER BY created_at ASC LIMIT :limit")
    suspend fun getOldest(limit: Int = 50): List<PendingReadingEntity>

    @Query("SELECT COUNT(*) FROM pending_readings")
    suspend fun pendingCount(): Int

    @Delete
    suspend fun delete(readings: List<PendingReadingEntity>)

    @Query("DELETE FROM pending_readings WHERE created_at < :cutoff")
    suspend fun pruneOlderThan(cutoff: Long)
}
