package com.hems.companion.data.preferences

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.credentialsDataStore by preferencesDataStore(name = "device_credentials")

/**
 * Persists the QR-issued credentials to DataStore. Backing file is excluded
 * from auto-backup / device-transfer (see res/xml/backup_rules.xml).
 */
@Singleton
class DeviceCredentialsStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private object Keys {
        val DEVICE_ID = intPreferencesKey("device_id")
        val DEVICE_KEY = stringPreferencesKey("device_key")
        val HMAC_SECRET = stringPreferencesKey("hmac_secret")
        val BACKEND_URL = stringPreferencesKey("backend_url")
        val CHARACTER_VERSION = stringPreferencesKey("character_version")
    }

    val credentials: Flow<DeviceCredentials?> = context.credentialsDataStore.data.map { prefs ->
        val id = prefs[Keys.DEVICE_ID] ?: return@map null
        val key = prefs[Keys.DEVICE_KEY] ?: return@map null
        val secret = prefs[Keys.HMAC_SECRET] ?: return@map null
        val url = prefs[Keys.BACKEND_URL] ?: return@map null
        DeviceCredentials(
            deviceId = id,
            deviceKey = key,
            hmacSecret = secret,
            backendUrl = url,
            characterVersion = prefs[Keys.CHARACTER_VERSION],
        )
    }

    suspend fun save(creds: DeviceCredentials) {
        context.credentialsDataStore.edit { prefs ->
            prefs[Keys.DEVICE_ID] = creds.deviceId
            prefs[Keys.DEVICE_KEY] = creds.deviceKey
            prefs[Keys.HMAC_SECRET] = creds.hmacSecret
            prefs[Keys.BACKEND_URL] = creds.backendUrl
            creds.characterVersion?.let { prefs[Keys.CHARACTER_VERSION] = it }
        }
    }

    suspend fun clear() {
        context.credentialsDataStore.edit { it.clear() }
    }
}
