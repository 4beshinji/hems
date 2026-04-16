package com.hems.companion.ui.setup

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import com.hems.companion.R

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
                        startQrScan(context) { raw ->
                            viewModel.onQrScanned(raw)
                        }
                    }) {
                        Text(stringResource(R.string.setup_scan_qr))
                    }
                }

                is SetupUiState.Registered -> {
                    Text(
                        text = stringResource(R.string.setup_already_registered, s.creds.deviceId),
                        style = MaterialTheme.typography.bodyLarge,
                    )
                    Spacer(Modifier.height(8.dp))
                    Text(
                        text = s.creds.backendUrl,
                        style = MaterialTheme.typography.labelMedium,
                    )
                    Spacer(Modifier.height(24.dp))
                    OutlinedButton(onClick = { viewModel.reset() }) {
                        Text(stringResource(R.string.setup_reset))
                    }
                }

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

private fun startQrScan(
    context: android.content.Context,
    onRaw: (String) -> Unit,
) {
    val options = GmsBarcodeScannerOptions.Builder()
        .enableAutoZoom()
        .build()
    val scanner = GmsBarcodeScanning.getClient(context, options)
    scanner.startScan()
        .addOnSuccessListener { barcode ->
            barcode.rawValue?.let(onRaw)
        }
        .addOnFailureListener { /* swallowed — UI remains in NotRegistered */ }
}
