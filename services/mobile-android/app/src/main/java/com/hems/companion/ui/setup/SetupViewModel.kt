package com.hems.companion.ui.setup

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hems.companion.data.preferences.DeviceCredentials
import com.hems.companion.data.repository.RegistrationRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

sealed interface SetupUiState {
    data object Loading : SetupUiState
    data object NotRegistered : SetupUiState
    data class Registered(val creds: DeviceCredentials) : SetupUiState
    data class Error(val message: String) : SetupUiState
}

@HiltViewModel
class SetupViewModel @Inject constructor(
    private val repo: RegistrationRepository,
) : ViewModel() {

    val state: StateFlow<SetupUiState> = kotlinx.coroutines.flow.flow {
        emit(SetupUiState.Loading as SetupUiState)
        repo.credentials.collect { creds ->
            emit(if (creds == null) SetupUiState.NotRegistered else SetupUiState.Registered(creds))
        }
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = SetupUiState.Loading,
    )

    fun onQrScanned(raw: String) {
        viewModelScope.launch {
            repo.registerFromQr(raw)
                .onFailure { err ->
                    _transient.value = SetupUiState.Error(err.message ?: "parse error")
                }
        }
    }

    fun reset() {
        viewModelScope.launch { repo.reset() }
    }

    private val _transient = kotlinx.coroutines.flow.MutableStateFlow<SetupUiState?>(null)
    val transient: StateFlow<SetupUiState?> = _transient

    fun clearTransient() {
        _transient.value = null
    }
}
