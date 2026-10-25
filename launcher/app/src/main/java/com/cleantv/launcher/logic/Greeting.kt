package com.cleantv.launcher.logic

object Greeting {
    enum class Kind { MORNING, AFTERNOON, NIGHT }

    fun forHour(hour: Int): Kind = when (hour) {
        in 5..11 -> Kind.MORNING
        in 12..17 -> Kind.AFTERNOON
        else -> Kind.NIGHT
    }
}
