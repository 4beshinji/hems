package com.hems.companion.ui.setup

import android.Manifest
import android.content.Intent
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import com.hems.companion.R
import com.hems.companion.service.SyncForegroundService

@Composable
fun SetupScreen(viewModel: SetupViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsState()
    val transient by viewModel.transient.collectAsState()
    val context = LocalContext.current

    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = stringResource(R.string.setup_title),
                style = MaterialTheme.typography.headlineMedium,
            )
            Spacer(Modifier.height(16.dp))

            when (val s = state) {
                SetupUiState.Loading -> Text("…")

                SetupUiState.NotRegistered -> {
                    Text(
                        text = stringResource(R.string.setup_description),
                        style = MaterialTheme.typography.bodyLarge,
                    )
                    Spacer(Modifier.height(24.dp))
                    Button(onClick = {
                        startQrScan(context) { raw -> viewModel.onQrScanned(raw) }
                    }) {
                        Text(stringResource(R.string.setup_scan_qr))
                    }
                }

                is SetupUiState.Registered -> RegisteredSection(
                    backendUrl = s.creds.backendUrl,
                    deviceId = s.creds.deviceId,
                    onReset = { viewModel.reset() },
                )

                is SetupUiState.Error -> Text(
                    text = stringResource(R.string.setup_error, s.message),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.error,
                )
            }

            transient?.let { t ->
                Spacer(Modifier.height(16.dp))
                if (t is SetupUiState.Error) {
                    Text(
                        stringResource(R.string.setup_error, t.message),
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                LaunchedEffect(t) {
                    kotlinx.coroutines.delay(3500)
                    viewModel.clearTransient()
                }
            }
        }
    }
}

/**
 * Post-registration UI: shows status + sync controls with permission flow.
 *
 * Permission chain: FINE+COARSE → BACKGROUND_LOCATION → ACTIVITY_RECOGNITION
 * → POST_NOTIFICATIONS (Android 13+) → start service.
 */
@Composable
private fun RegisteredSection(
    backendUrl: String,
    deviceId: Int,
    onReset: () -> Unit,
) {
    val context = LocalContext.current
    var syncRunning by remember { mutableStateOf(SyncForegroundService.isRunning) }
    var permissionStep by remember { mutableStateOf(0) }

    val bgLocationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) permissionStep = 2
        else permissionStep = -1
    }

    val activityLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { _ -> permissionStep = 3 }

    val notificationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { _ -> permissionStep = 4 }

    val fgLocationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        val fineGranted = results[Manifest.permission.ACCESS_FINE_LOCATION] == true
        val coarseGranted = results[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        if (fineGranted || coarseGranted) permissionStep = 1
        else permissionStep = -1
    }

    LaunchedEffect(permissionStep) {
        when (permissionStep) {
            1 -> bgLocationLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
            2 -> activityLauncher.launch(Manifest.permission.ACTIVITY_RECOGNITION)
            3 -> {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    notificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                } else {
                    permissionStep = 4
                }
            }
            4 -> {
                val intent = Intent(context, SyncForegroundService::class.java)
                ContextCompat.startForegroundService(context, intent)
                syncRunning = true
                permissionStep = 0
            }
        }
    }

    Text(
        text = stringResource(R.string.setup_already_registered, deviceId),
        style = MaterialTheme.typography.bodyLarge,
    )
    Spacer(Modifier.height(8.dp))
    Text(text = backendUrl, style = MaterialTheme.typography.labelMedium)
    Spacer(Modifier.height(24.dp))

    if (syncRunning) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("同期中", style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(6.dp))
            Text("●", color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.bodySmall)
        }
        Spacer(Modifier.height(12.dp))
        OutlinedButton(onClick = {
            context.stopService(Intent(context, SyncForegroundService::class.java))
            syncRunning = false
        }) {
            Text("同期を停止")
        }
    } else {
        if (permissionStep == -1) {
            Text(
                "位置情報の権限が必要です。設定から許可してください。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
            Spacer(Modifier.height(8.dp))
        }
        Button(onClick = {
            permissionStep = 0
            fgLocationLauncher.launch(arrayOf(
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION,
            ))
        }) {
            Text("センサー同期を開始")
        }
    }

    Spacer(Modifier.height(24.dp))
    OutlinedButton(onClick = onReset) {
        Text(stringResource(R.string.setup_reset))
    }
}

private fun startQrScan(
    context: android.content.Context,
    onRaw: (String) -> Unit,
) {
    val options = GmsBarcodeScannerOptions.Builder()
        .enableAutoZoom()
        .build()
    val scanner = GmsBarcodeScanning.getClient(context, options)
    scanner.startScan()
        .addOnSuccessListener { barcode -> barcode.rawValue?.let(onRaw) }
        .addOnFailureListener { /* swallowed — UI remains in NotRegistered */ }
}
