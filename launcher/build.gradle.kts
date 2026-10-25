plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "1.9.24" apply false
    // Gera prints das telas no computador, sem emulador (só nos testes; não entra no APK).
    id("app.cash.paparazzi") version "1.3.4" apply false
}
