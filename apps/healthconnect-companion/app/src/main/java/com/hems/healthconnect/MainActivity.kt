package com.hems.healthconnect

import android.os.Bundle
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.lifecycleScope
import com.hems.healthconnect.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var settings: SettingsRepository

    private val permissionLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        if (granted.containsAll(HealthConnectReader.REQUIRED_PERMISSIONS)) {
            Toast.makeText(this, "Permissions granted", Toast.LENGTH_SHORT).show()
        } else {
            Toast.makeText(this, "Some permissions denied", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        settings = SettingsRepository(this)
        loadSettings()
        updateStatus()

        binding.btnPermissions.setOnClickListener {
            permissionLauncher.launch(HealthConnectReader.REQUIRED_PERMISSIONS)
        }

        binding.btnSave.setOnClickListener {
            saveSettings()
        }

        binding.btnSyncNow.setOnClickListener {
            syncNow()
        }
    }

    private fun loadSettings() {
        binding.etBridgeUrl.setText(settings.bridgeUrl)
        binding.etWebhookSecret.setText(settings.webhookSecret)
        binding.etSyncInterval.setText(settings.syncIntervalMinutes.toString())
    }

    private fun saveSettings() {
        val url = binding.etBridgeUrl.text.toString().trim()
        if (url.isBlank()) {
            Toast.makeText(this, "Bridge URL is required", Toast.LENGTH_SHORT).show()
            return
        }

        settings.bridgeUrl = url
        settings.webhookSecret = binding.etWebhookSecret.text.toString().trim()

        val interval = binding.etSyncInterval.text.toString().toIntOrNull() ?: 15
        settings.syncIntervalMinutes = interval.coerceIn(15, 1440)

        // Schedule periodic sync
        DataSyncWorker.schedule(this, settings.syncIntervalMinutes)

        Toast.makeText(this, "Saved. Sync scheduled every ${settings.syncIntervalMinutes}min", Toast.LENGTH_SHORT).show()
    }

    private fun syncNow() {
        binding.tvStatus.text = getString(R.string.status_syncing)

        lifecycleScope.launch {
            val reader = HealthConnectReader(this@MainActivity)

            if (!reader.hasPermissions()) {
                binding.tvStatus.text = "Permissions not granted"
                return@launch
            }

            try {
                val dao = HemsDatabase.getInstance(this@MainActivity).pendingReadingDao()

                val data = withContext(Dispatchers.IO) {
                    reader.readLatest()
                }

                // Always queue locally first
                withContext(Dispatchers.IO) {
                    dao.insert(PendingReadingEntity(payloadJson = data.toString()))
                }

                if (!settings.isConfigured) {
                    val pending = withContext(Dispatchers.IO) { dao.pendingCount() }
                    binding.tvStatus.text = "Queued ($pending pending) — Bridge URL not configured"
                    return@launch
                }

                // Try to flush all pending
                val (sent, remaining) = withContext(Dispatchers.IO) {
                    val client = HemsBridgeClient(settings.bridgeUrl, settings.webhookSecret)
                    val pending = dao.getOldest(50)
                    val sentList = mutableListOf<PendingReadingEntity>()
                    for (entity in pending) {
                        try {
                            val payload = org.json.JSONObject(entity.payloadJson)
                            if (client.postReading(payload)) sentList.add(entity) else break
                        } catch (_: Exception) { break }
                    }
                    if (sentList.isNotEmpty()) dao.delete(sentList)
                    Pair(sentList.size, dao.pendingCount())
                }

                settings.lastSyncTimestamp = System.currentTimeMillis()
                settings.lastSyncStatus = if (remaining == 0) "success" else "partial: $remaining pending"
                updateStatus()
                Toast.makeText(this@MainActivity, "Sent $sent, $remaining pending", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                binding.tvStatus.text = "Error: ${e.message} (data queued locally)"
            }
        }
    }

    private fun updateStatus() {
        val ts = settings.lastSyncTimestamp
        val statusText = if (ts > 0) {
            val fmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
            getString(R.string.status_success, fmt.format(Date(ts)))
        } else {
            getString(R.string.status_idle)
        }

        // Show queue count in background
        lifecycleScope.launch {
            val pending = withContext(Dispatchers.IO) {
                HemsDatabase.getInstance(this@MainActivity).pendingReadingDao().pendingCount()
            }
            binding.tvStatus.text = if (pending > 0) {
                "$statusText (queue: $pending)"
            } else {
                statusText
            }
        }
    }
}
