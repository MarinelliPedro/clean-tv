package com.cleantv.launcher.ui

import android.content.Context
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.widget.FrameLayout
import android.widget.ImageView

/**
 * Atalho redondo só com ícone (Entradas, HDMI, TV ao vivo, Rede, Ajustes, Personalizar).
 * O nome aparece grande no título da tela quando ele ganha foco, então o topo fica limpo.
 */
class ShortcutButton(context: Context, s: Scale, kind: LineIcon.Kind, label: String) : FrameLayout(context) {
    private val icon = LineIcon(kind, white(0.82f))
    private val circleBg = GradientDrawable().apply {
        shape = GradientDrawable.OVAL
        setColor(white(0f))
    }

    var onFocus: ((Boolean) -> Unit)? = null

    init {
        isFocusable = true
        isFocusableInTouchMode = true
        isClickable = true
        contentDescription = label
        background = circleBg
        addView(ImageView(context).apply { setImageDrawable(icon) }, LayoutParams(s.px(30), s.px(30), Gravity.CENTER))

        setOnFocusChangeListener { _, focused ->
            circleBg.setColor(if (focused) white(0.94f) else white(0f))
            icon.setColor(if (focused) 0xFF0E1016.toInt() else white(0.82f))
            val scale = if (focused) 1.12f else 1f
            animate().scaleX(scale).scaleY(scale).setDuration(Motion.FOCUS_MS).setInterpolator(Motion.EASE).start()
            onFocus?.invoke(focused)
        }
    }
}
