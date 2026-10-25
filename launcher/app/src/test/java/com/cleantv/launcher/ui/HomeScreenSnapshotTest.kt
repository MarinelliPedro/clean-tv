package com.cleantv.launcher.ui

import android.content.ComponentName
import android.graphics.drawable.ColorDrawable
import app.cash.paparazzi.DeviceConfig
import app.cash.paparazzi.Paparazzi
import com.android.resources.Density
import com.android.resources.ScreenOrientation
import com.android.resources.ScreenRatio
import com.android.resources.ScreenSize
import com.cleantv.launcher.data.AppEntry
import com.cleantv.launcher.data.Art
import com.cleantv.launcher.logic.ArtColor
import org.junit.Rule
import org.junit.Test

/** Prints da tela inicial na resolução da TV do usuário (1280x720, 213 dpi). Gerados com recordPaparazziDebug. */
class HomeScreenSnapshotTest {
    @get:Rule
    val paparazzi = Paparazzi(
        deviceConfig = DeviceConfig(
            screenWidth = 1280,
            screenHeight = 720,
            xdpi = 213,
            ydpi = 213,
            density = Density.TV,
            orientation = ScreenOrientation.LANDSCAPE,
            ratio = ScreenRatio.LONG,
            size = ScreenSize.XLARGE,
            softButtons = false,
        ),
        theme = "android:Theme.DeviceDefault.NoActionBar",
    )

    private fun apps(): List<AppEntry> {
        val samples = listOf(
            "Netflix" to 0xFFB20710, "YouTube" to 0xFFD32F2F, "Prime Video" to 0xFF1A98FF,
            "Disney+" to 0xFF1E3FD0, "Globoplay" to 0xFFF2541B, "Max" to 0xFF5A2BE0,
            "Watch Brasil" to 0xFFE0A020, "Media Center" to 0xFF2E9E6B, "Play Store" to 0xFF2F9E5A,
            "TV" to 0xFFC62828,
        )
        return samples.map { (label, rgb) ->
            val color = rgb.toInt()
            val pkg = "app." + label.lowercase().filter { it.isLetter() }
            // Banner branco como o da Netflix real: o foco precisa aparecer mesmo assim.
            val banner = if (label == "Netflix") ColorDrawable(0xFFF4F4F4.toInt()) else Art.generatedBanner(paparazzi.context, null, label, color)
            AppEntry(pkg, ComponentName(pkg, "$pkg.Main"), label, banner, ArtColor.toGlow(color))
        }
    }

    private fun state(themeId: String = "noite", columns: Int = 5): HomeState {
        val all = apps()
        return HomeState(
            apps = all,
            dock = all.take(3),
            theme = Themes.byId(themeId),
            blackWallpaper = false,
            glow = true,
            columns = columns,
            clock24 = true,
            greeting = "Boa noite",
            recent = listOf(all[5], all[4], all[9]),
        )
    }

    @Test
    fun home() {
        val view = HomeScreen(paparazzi.context)
        view.bind(state())
        view.previewFocusDock(0)
        paparazzi.snapshot(view, "home")
    }

    @Test
    fun homeAuroraTheme() {
        val view = HomeScreen(paparazzi.context)
        view.bind(state(themeId = "aurora"))
        view.previewFocusDock(2)
        paparazzi.snapshot(view, "home_aurora")
    }

    @Test
    fun allAppsGrid() {
        val view = HomeScreen(paparazzi.context)
        view.bind(state())
        view.previewGrid()
        paparazzi.snapshot(view, "grid")
    }
}
