package com.hems.companion.data.preferences

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.serialization.json.Json

private val Context.capsuleDataStore by preferencesDataStore(name = "voice_capsule")

/**
 * Stores the currently-downloaded capsule manifest + the file-system paths
 * where each clip's MP3 has been cached. The cache directory itself is
 * under ``context.filesDir/capsule/`` and written by [CapsuleRepository].
 */
@Singleton
class CapsuleStore @Inject constructor(
    @ApplicationContext private val context: Context,
    private val json: Json,
) {
    private object Keys {
        val MANIFEST_JSON = stringPreferencesKey("manifest_json")
        val SCHEDULED_CLIP_IDS = stringSetPreferencesKey("scheduled_clip_ids")
    }

    val manifest: Flow<com.hems.companion.data.api.CapsuleManifest?> =
        context.capsuleDataStore.data.map { prefs ->
            prefs[Keys.MANIFEST_JSON]?.let {
                runCatching { json.decodeFromString(
                    com.hems.companion.data.api.CapsuleManifest.serializer(),
                    it,
                ) }.getOrNull()
            }
        }

    suspend fun saveManifest(manifest: com.hems.companion.data.api.CapsuleManifest) {
        val encoded = json.encodeToString(
            com.hems.companion.data.api.CapsuleManifest.serializer(), manifest,
        )
        context.capsuleDataStore.edit { prefs ->
            prefs[Keys.MANIFEST_JSON] = encoded
        }
    }

    suspend fun clear() {
        context.capsuleDataStore.edit { it.clear() }
    }

    /** Clip ids whose AlarmManager alarms are currently registered. */
    suspend fun scheduledClipIds(): Set<String> {
        return context.capsuleDataStore.data
            .map { it[Keys.SCHEDULED_CLIP_IDS] ?: emptySet() }
            .first()
    }

    suspend fun setScheduledClipIds(ids: Set<String>) {
        context.capsuleDataStore.edit { prefs ->
            prefs[Keys.SCHEDULED_CLIP_IDS] = ids
        }
    }
}
