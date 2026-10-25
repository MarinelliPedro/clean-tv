package com.cleantv.launcher.data

import android.content.Context
import android.content.SharedPreferences
import com.cleantv.launcher.logic.DockConfig

/** Preferências do launcher (tudo local; nada sai da TV). */
class LauncherPrefs(context: Context) {
    val prefs: SharedPreferences = context.getSharedPreferences("launcher", Context.MODE_PRIVATE)

    /** null = o usuário nunca configurou o dock. */
    var dock: List<String>?
        get() = if (prefs.contains(DOCK)) DockConfig.parse(prefs.getString(DOCK, "")) else null
        set(value) = prefs.edit().putString(DOCK, DockConfig.format(value.orEmpty())).apply()

    var order: List<String>
        get() = csv(ORDER)
        set(value) = prefs.edit().putString(ORDER, value.joinToString(",")).apply()

    var hidden: Set<String>
        get() = csv(HIDDEN).toSet()
        set(value) = prefs.edit().putString(HIDDEN, value.joinToString(",")).apply()

    var themeId: String
        get() = prefs.getString(THEME, "noite") ?: "noite"
        set(value) = prefs.edit().putString(THEME, value).apply()

    var blackWallpaper: Boolean
        get() = prefs.getBoolean(BLACK, false)
        set(value) = prefs.edit().putBoolean(BLACK, value).apply()

    var glow: Boolean
        get() = prefs.getBoolean(GLOW, true)
        set(value) = prefs.edit().putBoolean(GLOW, value).apply()

    var cinematic: Boolean
        get() = prefs.getBoolean(CINEMATIC, true)
        set(value) = prefs.edit().putBoolean(CINEMATIC, value).apply()

    /** Fundo em movimento (zoom lento na arte). */
    var motion: Boolean
        get() = prefs.getBoolean(MOTION, true)
        set(value) = prefs.edit().putBoolean(MOTION, value).apply()

    /** Apps abertos pelo launcher, o mais recente primeiro (ver [com.cleantv.launcher.logic.Recents]). */
    var recent: List<String>
        get() = csv(RECENT)
        set(value) = prefs.edit().putString(RECENT, value.joinToString(",")).apply()

    var columns: Int
        get() = prefs.getInt(COLUMNS, 5).coerceIn(4, 6)
        set(value) = prefs.edit().putInt(COLUMNS, value.coerceIn(4, 6)).apply()

    var clock24: Boolean
        get() = prefs.getBoolean(CLOCK24, true)
        set(value) = prefs.edit().putBoolean(CLOCK24, value).apply()

    var greeting: Boolean
        get() = prefs.getBoolean(GREETING, true)
        set(value) = prefs.edit().putBoolean(GREETING, value).apply()

    private fun csv(key: String): List<String> =
        prefs.getString(key, "").orEmpty().split(',').map { it.trim() }.filter { it.isNotEmpty() }

    companion object {
        const val RECENT = "recent"
        private const val MOTION = "motion"
        private const val DOCK = "dock"
        private const val ORDER = "order"
        private const val HIDDEN = "hidden"
        private const val THEME = "theme"
        private const val BLACK = "black_wallpaper"
        private const val GLOW = "glow"
        private const val CINEMATIC = "cinematic"
        private const val COLUMNS = "columns"
        private const val CLOCK24 = "clock24"
        private const val GREETING = "greeting"
    }
}
