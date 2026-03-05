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
                val data = withContext(Dispatchers.IO) {
                    reader.readLatest()
                }

                if (!settings.isConfigured) {
                    binding.tvStatus.text = "Bridge URL not configured"
                    return@launch
                }

                val success = withContext(Dispatchers.IO) {
                    val client = HemsBridgeClient(settings.bridgeUrl, settings.webhookSecret)
                    client.postReading(data)
                }

                if (success) {
                    settings.lastSyncTimestamp = System.currentTimeMillis()
                    settings.lastSyncStatus = "success"
                    updateStatus()
                    Toast.makeText(this@MainActivity, "Sync OK (${data.length()} fields)", Toast.LENGTH_SHORT).show()
                } else {
                    binding.tvStatus.text = "Bridge returned error"
                }
            } catch (e: Exception) {
                binding.tvStatus.text = "Error: ${e.message}"
            }
        }
    }

    private fun updateStatus() {
        val ts = settings.lastSyncTimestamp
        if (ts > 0) {
            val fmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
            binding.tvStatus.text = getString(R.string.status_success, fmt.format(Date(ts)))
        } else {
            binding.tvStatus.text = getString(R.string.status_idle)
        }
    }
}
