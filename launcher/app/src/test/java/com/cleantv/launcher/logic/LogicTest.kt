package com.cleantv.launcher.logic

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AppOrderingTest {
    private data class App(val pkg: String, val label: String)

    private val apps = listOf(App("c", "Netflix"), App("a", "YouTube"), App("b", "Disney+"), App("d", "Ágora"))

    @Test
    fun savedOrderFirstThenAlphabeticalIgnoringAccents() {
        val ordered = AppOrdering.order(apps, listOf("a", "zz", "a"), { it.pkg }, { it.label })
        assertEquals(listOf("a", "d", "b", "c"), ordered.map { it.pkg })
    }

    @Test
    fun moveStaysInsideBounds() {
        assertEquals(listOf("b", "a", "c"), AppOrdering.move(listOf("a", "b", "c"), "a", 1))
        assertEquals(listOf("a", "b", "c"), AppOrdering.move(listOf("a", "b", "c"), "a", -1))
        assertEquals(listOf("a", "b", "c"), AppOrdering.move(listOf("a", "b", "c"), "x", 1))
    }
}

class DockConfigTest {
    @Test
    fun parseKeepsOnlyValidUniquePackagesUpToFour() {
        assertEquals(
            listOf("com.netflix.ninja", "com.a.b", "com.c.d", "com.e.f"),
            DockConfig.parse(" com.netflix.ninja,com.a.b,bad name,com.a.b;rm,com.c.d,com.e.f,com.g.h"),
        )
        assertEquals(emptyList<String>(), DockConfig.parse(null))
    }

    @Test
    fun neverConfiguredUsesInstalledSuggestions() {
        val installed = listOf("com.amazon.amazonvideo.livingroom", "com.netflix.ninja", "x.y")
        assertEquals(listOf("com.netflix.ninja", "com.amazon.amazonvideo.livingroom"), DockConfig.resolve(null, installed))
        assertEquals(emptyList<String>(), DockConfig.resolve(emptyList(), installed))
        assertEquals(listOf("x.y"), DockConfig.resolve(listOf("x.y", "not.installed"), installed))
    }

    @Test
    fun addAndRemove() {
        assertEquals(listOf("a.b", "c.d"), DockConfig.add(listOf("a.b"), "c.d"))
        assertNull(DockConfig.add(listOf("a.a", "b.b", "c.c", "d.d"), "e.e"))
        assertEquals(listOf("a.b"), DockConfig.remove(listOf("a.b", "c.d"), "c.d"))
    }
}

class GreetingTest {
    @Test
    fun hours() {
        assertEquals(Greeting.Kind.NIGHT, Greeting.forHour(4))
        assertEquals(Greeting.Kind.MORNING, Greeting.forHour(5))
        assertEquals(Greeting.Kind.AFTERNOON, Greeting.forHour(12))
        assertEquals(Greeting.Kind.NIGHT, Greeting.forHour(18))
    }
}

class BlurTest {
    @Test
    fun spreadsASinglePixelAndKeepsSolidAreasSolid() {
        val pixels = IntArray(25) { 0xFF000000.toInt() }.also { it[12] = 0xFFFFFFFF.toInt() }
        val blurred = Blur.box(pixels, 5, 5, radius = 1, passes = 1)
        assertTrue(blurred[12] and 0xFF in 1..254)
        assertTrue(blurred[11] and 0xFF > 0)
        val solid = IntArray(12) { 0xFF336699.toInt() }
        assertEquals(solid.toList(), Blur.box(solid, 4, 3, radius = 2).toList())
    }
}

class ArtColorTest {
    private fun hue(color: Int) = ArtColor.rgbToHsv(color)[0]

    @Test
    fun logoColorWinsOverBlackAndWhiteBackground() {
        val red = 0xFFE50914.toInt()
        val pixels = IntArray(100) { if (it < 10) red else if (it % 2 == 0) 0xFF000000.toInt() else 0xFFFFFFFF.toInt() }
        val glow = ArtColor.pick(pixels)
        assertTrue("matiz vermelho esperado, veio ${hue(glow)}", hue(glow) < 10f || hue(glow) > 350f)
        assertTrue(ArtColor.rgbToHsv(glow)[2] >= 0.75f)
    }

    @Test
    fun grayArtStaysNeutralAndEmptyUsesFallback() {
        val gray = ArtColor.pick(IntArray(50) { 0xFF808080.toInt() })
        assertTrue(ArtColor.rgbToHsv(gray)[1] < 0.15f)
        assertEquals(ArtColor.FALLBACK, ArtColor.pick(IntArray(10) { 0x00FFFFFF }))
    }

    @Test
    fun hsvRoundTrip() {
        val blue = 0xFF1A98FF.toInt()
        val hsv = ArtColor.rgbToHsv(blue)
        assertEquals(blue, ArtColor.hsvToRgb(hsv[0], hsv[1], hsv[2]))
    }
}

class RecentsTest {
    @Test
    fun recordPutsTheAppFirstWithoutDuplicatesAndKeepsTheLimit() {
        assertEquals(listOf("b", "a", "c"), Recents.record(listOf("a", "b", "c"), "b"))
        assertEquals(listOf("x", "a", "b"), Recents.record(listOf("a", "b", "c"), "x", max = 3))
    }

    @Test
    fun visibleSkipsDockHiddenAndUninstalledApps() {
        val recent = listOf("netflix", "globo", "removido", "disney", "max", "oculto")
        val available = setOf("netflix", "globo", "disney", "max")
        assertEquals(listOf("globo", "disney"), Recents.visible(recent, available, dock = listOf("netflix"), limit = 2))
        assertEquals(emptyList<String>(), Recents.visible(emptyList(), available, dock = emptyList(), limit = 5))
    }
}
