package com.cleantv.launcher

import android.app.Activity
import android.app.AlertDialog
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.media.tv.TvContract
import android.media.tv.TvInputInfo
import android.media.tv.TvInputManager
import android.provider.Settings
import android.widget.Toast

/** Atalhos de TV: entradas (HDMI/AV), TV ao vivo, rede e configurações. */
object TvShortcuts {
    /** Menus de fonte dos fabricantes (abrem o seletor nativo da TV). */
    private val SOURCE_MENUS = listOf(
        ComponentName("com.tcl.sourcemananger", "com.tcl.sourcemanager.MainActivity"),
    )

    /** Apps de TV ao vivo conhecidos, em ordem de preferência. */
    private val LIVE_TV_PACKAGES = listOf(
        "com.tcl.tv",
        "com.google.android.tv",
        "com.android.tv",
        "com.mediatek.wwtv.tvcenter",
        "com.sony.dtv.tvx",
        "com.xiaomi.mitv.tvplayer",
    )

    fun openInputs(activity: Activity) {
        for (component in SOURCE_MENUS) {
            if (start(activity, Intent().setComponent(component))) return
        }
        showInputs(activity, passthroughOnly = false)
    }

    fun showInputs(activity: Activity, passthroughOnly: Boolean) {
        val manager = activity.getSystemService(Context.TV_INPUT_SERVICE) as? TvInputManager
        val inputs = manager?.tvInputList.orEmpty()
            .filter { !it.isHidden(activity) && (!passthroughOnly || it.isPassthroughInput) }
        if (inputs.isEmpty()) {
            Toast.makeText(activity, R.string.no_inputs, Toast.LENGTH_SHORT).show()
            return
        }
        AlertDialog.Builder(activity, android.R.style.Theme_DeviceDefault_Dialog_Alert)
            .setTitle(R.string.inputs_title)
            .setItems(inputs.map { it.loadLabel(activity) }.toTypedArray()) { _, which -> openInput(activity, inputs[which]) }
            .show()
    }

    private fun openInput(activity: Activity, input: TvInputInfo) {
        val uri = if (input.isPassthroughInput) {
            TvContract.buildChannelUriForPassthroughInput(input.id)
        } else {
            TvContract.buildChannelsUriForInput(input.id)
        }
        if (!start(activity, Intent(Intent.ACTION_VIEW, uri))) openLiveTv(activity)
    }

    fun openLiveTv(activity: Activity) {
        for (pkg in LIVE_TV_PACKAGES) {
            val intent = activity.packageManager.getLeanbackLaunchIntentForPackage(pkg) ?: continue
            if (start(activity, intent)) return
        }
        Toast.makeText(activity, R.string.no_live_tv, Toast.LENGTH_SHORT).show()
    }

    fun openNetwork(activity: Activity) {
        start(activity, Intent(Settings.ACTION_WIFI_SETTINGS)) ||
            start(activity, Intent(Settings.ACTION_WIRELESS_SETTINGS)) ||
            start(activity, Intent(Settings.ACTION_SETTINGS))
    }

    fun openSettings(activity: Activity) {
        start(activity, Intent(Settings.ACTION_SETTINGS))
    }

    private fun start(activity: Activity, intent: Intent): Boolean = try {
        activity.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        true
    } catch (e: Exception) {
        false
    }
}
