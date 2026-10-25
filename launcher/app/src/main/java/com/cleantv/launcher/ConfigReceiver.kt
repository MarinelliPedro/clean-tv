package com.cleantv.launcher

import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.cleantv.launcher.data.LauncherPrefs
import com.cleantv.launcher.logic.DockConfig
import com.cleantv.launcher.ui.Themes

/**
 * Configuração vinda da ferramenta do computador, por exemplo:
 *   adb shell am broadcast -n com.cleantv.launcher/.ConfigReceiver \
 *     -a com.cleantv.launcher.action.CONFIGURE --es dock com.netflix.ninja,com.google.android.youtube.tv
 * Protegido por WRITE_SECURE_SETTINGS (só o shell do ADB e o sistema conseguem enviar).
 */
class ConfigReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_CONFIGURE) return
        val prefs = LauncherPrefs(context)
        intent.getStringExtra(EXTRA_DOCK)?.let { prefs.dock = DockConfig.parse(it) }
        intent.getStringExtra(EXTRA_THEME)?.let { id -> if (Themes.ALL.any { it.id == id }) prefs.themeId = id }
        resultCode = Activity.RESULT_OK
        resultData = "dock=" + DockConfig.format(prefs.dock.orEmpty()) + ";theme=" + prefs.themeId
    }

    companion object {
        const val ACTION_CONFIGURE = "com.cleantv.launcher.action.CONFIGURE"
        const val EXTRA_DOCK = "dock"
        const val EXTRA_THEME = "theme"
    }
}
