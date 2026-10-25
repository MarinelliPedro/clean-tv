package com.cleantv.launcher.data

import android.content.ComponentName
import android.graphics.Bitmap
import android.graphics.drawable.Drawable

data class AppEntry(
    val packageName: String,
    val component: ComponentName,
    val label: String,
    /** Banner 16:9 do app, ou um banner gerado a partir do ícone. */
    val banner: Drawable,
    /** Cor do brilho de fundo quando o app está em foco. */
    val artColor: Int,
    /** Miniatura do banner para o fundo cinematográfico (preparada fora da thread de interface). */
    val backdrop: Bitmap? = null,
)
