package com.cleantv.launcher.logic

import java.text.Collator

/** Ordem dos apps na grade: primeiro a ordem que o usuário salvou, depois o resto em ordem alfabética. */
object AppOrdering {

    private val collator: Comparator<Any?> = Collator.getInstance().apply { strength = Collator.PRIMARY }

    fun <T> order(items: List<T>, saved: List<String>, key: (T) -> String, label: (T) -> String): List<T> {
        val byKey = items.associateBy(key)
        val first = saved.distinct().mapNotNull { byKey[it] }
        val placed = first.map(key).toSet()
        val rest = items.filter { key(it) !in placed }.sortedWith(compareBy(collator) { label(it) })
        return first + rest
    }

    /** Move `key` em `delta` posições dentro de `order` (limitado às bordas). */
    fun move(order: List<String>, key: String, delta: Int): List<String> {
        val from = order.indexOf(key)
        if (from < 0) return order
        val to = (from + delta).coerceIn(0, order.lastIndex)
        if (to == from) return order
        return order.toMutableList().apply {
            removeAt(from)
            add(to, key)
        }
    }
}
