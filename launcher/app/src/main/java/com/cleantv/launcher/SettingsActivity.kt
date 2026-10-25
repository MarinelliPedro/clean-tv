package com.cleantv.launcher

import android.app.Activity
import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.StateListDrawable
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.cleantv.launcher.data.LauncherPrefs
import com.cleantv.launcher.ui.GlassDrawable
import com.cleantv.launcher.ui.Scale
import com.cleantv.launcher.ui.Themes
import com.cleantv.launcher.ui.Weight
import com.cleantv.launcher.ui.textStyle
import com.cleantv.launcher.ui.white

/** "Personalizar": cada linha alterna o valor com OK. */
class SettingsActivity : Activity() {
    private lateinit var prefs: LauncherPrefs
    private lateinit var s: Scale

    private class Row(val title: Int, val value: () -> String, val onClick: () -> Unit)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = LauncherPrefs(this)
        s = Scale.of(this)
        render()
    }

    private fun rows(): List<Row> = listOf(
        Row(R.string.settings_theme, { getString(Themes.byId(prefs.themeId).labelRes) }) {
            val index = Themes.ALL.indexOf(Themes.byId(prefs.themeId))
            prefs.themeId = Themes.ALL[(index + 1) % Themes.ALL.size].id
        },
        Row(R.string.settings_wallpaper, {
            getString(if (prefs.blackWallpaper) R.string.value_wallpaper_black else R.string.value_wallpaper_theme)
        }) { prefs.blackWallpaper = !prefs.blackWallpaper },
        Row(R.string.settings_glow, { onOff(prefs.glow) }) { prefs.glow = !prefs.glow },
        Row(R.string.settings_backdrop, { onOff(prefs.cinematic) }) { prefs.cinematic = !prefs.cinematic },
        Row(R.string.settings_motion, { onOff(prefs.motion) }) { prefs.motion = !prefs.motion },
        Row(R.string.settings_columns, { prefs.columns.toString() }) {
            prefs.columns = if (prefs.columns >= 6) 4 else prefs.columns + 1
        },
        Row(R.string.settings_clock, {
            getString(if (prefs.clock24) R.string.value_clock_24 else R.string.value_clock_12)
        }) { prefs.clock24 = !prefs.clock24 },
        Row(R.string.settings_greeting, { onOff(prefs.greeting) }) { prefs.greeting = !prefs.greeting },
        Row(R.string.settings_hidden, { getString(R.string.value_hidden, prefs.hidden.size) }) { prefs.hidden = emptySet() },
        Row(R.string.settings_order, { getString(R.string.value_order) }) { prefs.order = emptyList() },
        Row(R.string.settings_screensaver, { getString(R.string.value_screensaver) }) {
            runCatching { startActivity(Intent(Settings.ACTION_DREAM_SETTINGS)) }
        },
        Row(R.string.settings_about, { getString(R.string.value_about, BuildConfigCompat.versionName(this)) }) {},
    )

    private fun onOff(value: Boolean) = getString(if (value) R.string.value_on else R.string.value_off)

    private fun render() {
        val theme = Themes.byId(prefs.themeId)
        val list = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(s.px(160), s.px(80), s.px(160), s.px(80))
            background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, intArrayOf(theme.top, theme.bottom))
        }
        list.addView(TextView(this).apply {
            textStyle(s, 56, white(1f), Weight.SEMIBOLD)
            text = getString(R.string.settings_title)
        }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = s.px(40) })

        val valueViews = mutableListOf<Pair<TextView, Row>>()
        for (row in rows()) {
            val line = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                isFocusable = true
                isClickable = true
                setPadding(s.px(32), s.px(22), s.px(32), s.px(22))
                background = StateListDrawable().apply {
                    addState(intArrayOf(android.R.attr.state_focused), GlassDrawable(s.f(18), s.f(2).coerceAtLeast(1f), 1.6f))
                    addState(intArrayOf(), GradientDrawable())
                }
            }
            val title = TextView(this).apply { textStyle(s, 30, white(0.92f)); text = getString(row.title) }
            val value = TextView(this).apply { textStyle(s, 28, theme.accent); text = row.value() }
            line.addView(title, LinearLayout.LayoutParams(0, -2, 1f))
            line.addView(value)
            line.setOnClickListener {
                row.onClick()
                valueViews.forEach { (view, r) -> view.text = r.value() }
            }
            valueViews += value to row
            list.addView(line, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = s.px(8) })
        }
        setContentView(ScrollView(this).apply {
            isVerticalScrollBarEnabled = false
            addView(list)
        })
        list.getChildAt(1)?.requestFocus()
    }
}

/** Versão do app sem depender do BuildConfig gerado. */
internal object BuildConfigCompat {
    fun versionName(activity: Activity): String =
        runCatching { activity.packageManager.getPackageInfo(activity.packageName, 0).versionName }.getOrNull() ?: "?"
}
