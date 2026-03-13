package com.hems.healthconnect

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(entities = [PendingReadingEntity::class], version = 1, exportSchema = false)
abstract class HemsDatabase : RoomDatabase() {
    abstract fun pendingReadingDao(): PendingReadingDao

    companion object {
        @Volatile
        private var INSTANCE: HemsDatabase? = null

        fun getInstance(context: Context): HemsDatabase =
            INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    HemsDatabase::class.java,
                    "hems_readings.db",
                ).build().also { INSTANCE = it }
            }
    }
}
