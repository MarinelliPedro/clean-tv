package com.cleantv.launcher

import android.graphics.Color
import android.os.Handler
import android.os.Looper
import android.service.dreams.DreamService
import android.view.Gravity
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextClock
import com.cleantv.launcher.data.LauncherPrefs
import com.cleantv.launcher.ui.Scale
import com.cleantv.launcher.ui.Weight
import com.cleantv.launcher.ui.textStyle
import com.cleantv.launcher.ui.white
import kotlin.random.Random

/** Protetor de tela: relógio e data em fundo preto, mudando de lugar a cada minuto (evita marcas na tela). */
class ClockDreamService : DreamService() {
    private val handler = Handler(Looper.getMainLooper())
    private var box: LinearLayout? = null

    private val mover = object : Runnable {
        override fun run() {
            move()
            handler.postDelayed(this, 60_000)
        }
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        isInteractive = false
        isFullscreen = true
        isScreenBright = false
        val s = Scale.of(this)
        val clock24 = LauncherPrefs(this).clock24
        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
        }
        content.addView(TextClock(this).apply {
            textStyle(s, 168, white(0.85f), Weight.MEDIUM)
            fontFeatureSettings = "tnum"
            val format = if (clock24) "HH:mm" else "h:mm"
            format24Hour = format
            format12Hour = format
        })
        content.addView(TextClock(this).apply {
            textStyle(s, 34, white(0.5f))
            format24Hour = "EEEE, d 'de' MMMM"
            format12Hour = "EEEE, d 'de' MMMM"
        })
        root.addView(content, FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT))
        box = content
        setContentView(root)
        handler.postDelayed(mover, 500)
    }

    private fun move() {
        val view = box ?: return
        val parent = view.parent as? FrameLayout ?: return
        val maxX = (parent.width - view.width).coerceAtLeast(1)
        val maxY = (parent.height - view.height).coerceAtLeast(1)
        view.animate().alpha(0f).setDuration(600).withEndAction {
            view.x = Random.nextInt(maxX).toFloat()
            view.y = Random.nextInt(maxY).toFloat()
            view.animate().alpha(1f).setDuration(600).start()
        }.start()
    }

    override fun onDetachedFromWindow() {
        handler.removeCallbacksAndMessages(null)
        super.onDetachedFromWindow()
    }
}
