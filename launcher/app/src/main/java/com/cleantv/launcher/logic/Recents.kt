package com.cleantv.launcher.logic

/** Apps abertos recentemente, o mais recente primeiro. A lista fica só na TV. */
object Recents {
    const val MAX = 12

    fun record(recent: List<String>, pkg: String, max: Int = MAX): List<String> =
        (listOf(pkg) + recent.filter { it != pkg }).take(max)

    /**
     * O que a fileira "Recentes" mostra: apps que ainda existem e não estão ocultos, fora do dock
     * (que já está a um clique), no máximo uma linha da grade.
     */
    fun visible(recent: List<String>, available: Set<String>, dock: Collection<String>, limit: Int): List<String> =
        recent.distinct().filter { it in available && it !in dock }.take(limit)
}
