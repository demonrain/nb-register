package com.nbregister.whatsappforwarder

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.nbregister.whatsappforwarder.network.OtpWebhookClient
import com.nbregister.whatsappforwarder.service.WhatsAppNotificationListenerService
import com.nbregister.whatsappforwarder.settings.SettingsStore
import com.nbregister.whatsappforwarder.ui.AppTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            AppTheme {
                WhatsAppForwarderScreen()
            }
        }
    }
}

@Composable
private fun WhatsAppForwarderScreen() {
    val context = LocalContext.current
    val settingsStore = remember { SettingsStore(context) }
    val scope = rememberCoroutineScope()

    var webhookUrl by remember { mutableStateOf(settingsStore.webhookUrl) }
    var forwardingEnabled by remember { mutableStateOf(settingsStore.forwardingEnabled) }
    var requireKeyword by remember { mutableStateOf(settingsStore.requireKeyword) }
    var keywordsRaw by remember { mutableStateOf(settingsStore.keywordsRaw) }
    var packagesRaw by remember { mutableStateOf(settingsStore.whatsappPackagesRaw) }

    Surface(
        color = MaterialTheme.colorScheme.background,
        modifier = Modifier.fillMaxSize(),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text("WhatsApp Forwarder", style = MaterialTheme.typography.headlineSmall)
            Text(
                "Forward WhatsApp OTP notifications to the GoPay webhook.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.secondary,
            )

            StatusSection(context)

            SectionCard {
                ToggleRow(
                    title = "Forwarding",
                    description = "Listen for watched WhatsApp packages and send OTP messages.",
                    checked = forwardingEnabled,
                    onCheckedChange = { forwardingEnabled = it },
                )
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = webhookUrl,
                    onValueChange = { webhookUrl = it },
                    label = { Text("Webhook URL") },
                    placeholder = { Text("http://192.168.0.115:8081/webhook/otp") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(10.dp))
                ToggleRow(
                    title = "Require keyword",
                    description = "Reduces false positives before sending a numeric code.",
                    checked = requireKeyword,
                    onCheckedChange = { requireKeyword = it },
                )
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = keywordsRaw,
                    onValueChange = { keywordsRaw = it },
                    label = { Text("OTP keywords") },
                    minLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = packagesRaw,
                    onValueChange = { packagesRaw = it },
                    label = { Text("Watched packages") },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(14.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Button(
                        onClick = {
                            settingsStore.webhookUrl = webhookUrl
                            settingsStore.forwardingEnabled = forwardingEnabled
                            settingsStore.requireKeyword = requireKeyword
                            settingsStore.keywordsRaw = keywordsRaw
                            settingsStore.whatsappPackagesRaw = packagesRaw
                            toast(context, "Saved")
                        },
                    ) {
                        Text("Save")
                    }
                    OutlinedButton(
                        onClick = {
                            scope.launch {
                                settingsStore.webhookUrl = webhookUrl
                                settingsStore.forwardingEnabled = forwardingEnabled
                                settingsStore.requireKeyword = requireKeyword
                                settingsStore.keywordsRaw = keywordsRaw
                                settingsStore.whatsappPackagesRaw = packagesRaw

                                val settings = settingsStore.readAll()
                                if (!settings.forwardingEnabled) {
                                    toast(context, "Forwarding disabled")
                                    return@launch
                                }
                                if (settings.webhookUrl.isBlank()) {
                                    toast(context, "Webhook URL required")
                                    return@launch
                                }

                                val result = withContext(Dispatchers.IO) {
                                    OtpWebhookClient().send(settings.webhookUrl, "123456")
                                }
                                toast(context, if (result.success) "Test sent" else "Test failed: ${result.message}")
                            }
                        },
                    ) {
                        Text("Test")
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusSection(context: Context) {
    val notificationAccess = remember { mutableStateOf(isNotificationAccessEnabled(context)) }
    SectionCard {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text("Notification access", style = MaterialTheme.typography.titleMedium)
                Text(
                    if (notificationAccess.value) "Enabled" else "Not enabled",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.secondary,
                )
            }
            Button(
                onClick = {
                    context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    notificationAccess.value = isNotificationAccessEnabled(context)
                },
            ) {
                Text("Open")
            }
        }
        Spacer(Modifier.height(10.dp))
        OutlinedButton(
            onClick = {
                runCatching {
                    context.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                }
            },
        ) {
            Text("Battery settings")
        }
    }
}

@Composable
private fun SectionCard(content: @Composable () -> Unit) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp)) {
            content()
        }
    }
}

@Composable
private fun ToggleRow(
    title: String,
    description: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(description, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.secondary)
        }
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

private fun isNotificationAccessEnabled(context: Context): Boolean {
    val enabled = Settings.Secure.getString(
        context.contentResolver,
        "enabled_notification_listeners",
    ) ?: return false
    val expected = ComponentName(
        context,
        WhatsAppNotificationListenerService::class.java,
    ).flattenToString()
    return enabled.split(':').any { item ->
        item.equals(expected, ignoreCase = true) || item.contains(context.packageName, ignoreCase = true)
    }
}

private fun toast(context: Context, text: String) {
    Toast.makeText(context.applicationContext, text, Toast.LENGTH_SHORT).show()
}
