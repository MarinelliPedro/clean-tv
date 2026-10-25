package com.cleantv.launcher.logic

/** Regras do dock: até 4 apps, só pacotes válidos e instalados, sem repetição. */
object DockConfig {
    const val SIZE = 4

    private val PACKAGE = Regex("^[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+$")

    /** Usados enquanto o usuário nunca configurou o dock. */
    val SUGGESTIONS = listOf(
        "com.netflix.ninja",
        "com.google.android.youtube.tv",
        "com.amazon.amazonvideo.livingroom",
        "com.disney.disneyplus",
        "com.apple.atve.androidtv.appletv",
        "com.globo.globotv",
        "com.wbd.stream",
    )

    fun parse(csv: String?): List<String> =
        csv.orEmpty().split(',').map { it.trim() }.filter { PACKAGE.matches(it) }.distinct().take(SIZE)

    fun format(packages: List<String>): String = packages.joinToString(",")

    /** `saved == null` significa "nunca configurado": usa as sugestões que estiverem instaladas. */
    fun resolve(saved: List<String>?, installed: Collection<String>): List<String> {
        val available = installed.toSet()
        val source = saved ?: SUGGESTIONS
        return source.filter { it in available }.distinct().take(SIZE)
    }

    /** Retorna o novo dock, ou null se ele já estiver cheio. */
    fun add(dock: List<String>, pkg: String): List<String>? = when {
        pkg in dock -> dock
        dock.size >= SIZE -> null
        else -> dock + pkg
    }

    fun remove(dock: List<String>, pkg: String): List<String> = dock - pkg
}
