package com.cleantv.launcher.data

import android.content.ComponentName
import android.content.Context
import android.content.Intent

/** Lista os apps que aparecem na tela inicial da TV (categoria LEANBACK_LAUNCHER). */
class AppRepository(private val context: Context) {

    fun load(): List<AppEntry> {
        val pm = context.packageManager
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LEANBACK_LAUNCHER)
        val seen = HashSet<String>()
        val apps = ArrayList<AppEntry>()
        for (info in pm.queryIntentActivities(intent, 0)) {
            val activity = info.activityInfo ?: continue
            val pkg = activity.packageName
            if (pkg == context.packageName || !seen.add(pkg)) continue
            runCatching {
                val label = info.loadLabel(pm)?.toString()?.trim().takeUnless { it.isNullOrEmpty() } ?: pkg
                val banner = activity.loadBanner(pm) ?: Art.generatedBanner(context, info.loadIcon(pm), label)
                apps += AppEntry(pkg, ComponentName(pkg, activity.name), label, banner, Art.colorOf(banner), Art.thumbnail(banner))
            }
        }
        return apps
    }
}
