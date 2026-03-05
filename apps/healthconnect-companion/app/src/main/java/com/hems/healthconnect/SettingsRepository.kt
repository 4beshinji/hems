package com.hems.healthconnect

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit

class SettingsRepository(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences("hems_settings", Context.MODE_PRIVATE)

    var bridgeUrl: String
        get() = prefs.getString(KEY_BRIDGE_URL, "") ?: ""
        set(value) = prefs.edit { putString(KEY_BRIDGE_URL, value) }

    var webhookSecret: String
        get() = prefs.getString(KEY_WEBHOOK_SECRET, "") ?: ""
        set(value) = prefs.edit { putString(KEY_WEBHOOK_SECRET, value) }

    var syncIntervalMinutes: Int
        get() = prefs.getInt(KEY_SYNC_INTERVAL, 15)
        set(value) = prefs.edit { putInt(KEY_SYNC_INTERVAL, value) }

    var lastSyncTimestamp: Long
        get() = prefs.getLong(KEY_LAST_SYNC, 0L)
        set(value) = prefs.edit { putLong(KEY_LAST_SYNC, value) }

    var lastSyncStatus: String
        get() = prefs.getString(KEY_LAST_STATUS, "idle") ?: "idle"
        set(value) = prefs.edit { putString(KEY_LAST_STATUS, value) }

    val isConfigured: Boolean
        get() = bridgeUrl.isNotBlank()

    companion object {
        private const val KEY_BRIDGE_URL = "bridge_url"
        private const val KEY_WEBHOOK_SECRET = "webhook_secret"
        private const val KEY_SYNC_INTERVAL = "sync_interval_minutes"
        private const val KEY_LAST_SYNC = "last_sync_ts"
        private const val KEY_LAST_STATUS = "last_sync_status"
    }
}
