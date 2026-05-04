package com.hems.companion.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.work.Data
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager

/**
 * Alarm target — fired by [CapsuleAlarmScheduler]. Hands the play request
 * off to a [CapsulePlaybackWorker] so MediaPlayer has a proper coroutine
 * lifecycle (broadcasts have a hard ~10s budget).
 */
class CapsulePlaybackReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_PLAY) return
        val capsuleId = intent.getStringExtra(EXTRA_CAPSULE_ID) ?: return
        val clipId = intent.getStringExtra(EXTRA_CLIP_ID) ?: return
        val audioUrl = intent.getStringExtra(EXTRA_AUDIO_URL) ?: return

        val data = Data.Builder()
            .putString(CapsulePlaybackWorker.KEY_CAPSULE_ID, capsuleId)
            .putString(CapsulePlaybackWorker.KEY_CLIP_ID, clipId)
            .putString(CapsulePlaybackWorker.KEY_AUDIO_URL, audioUrl)
            .putLong(CapsulePlaybackWorker.KEY_SCHEDULED_AT_MS, System.currentTimeMillis())
            .build()
        val request = OneTimeWorkRequestBuilder<CapsulePlaybackWorker>()
            .setInputData(data)
            .addTag(CapsulePlaybackWorker.TAG)
            .build()
        WorkManager.getInstance(context).enqueue(request)
    }

    companion object {
        const val ACTION_PLAY = "com.hems.companion.PLAY_CAPSULE_CLIP"
        const val EXTRA_CAPSULE_ID = "capsule_id"
        const val EXTRA_CLIP_ID = "clip_id"
        const val EXTRA_AUDIO_URL = "audio_url"
    }
}
