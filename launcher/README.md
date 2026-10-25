# Launcher Clean TV

Tela inicial minimalista para Android TV / Google TV, parte do projeto Clean TV.

- Kotlin + Views nativas, **sem bibliotecas** (nem AndroidX) e **sem permissão de internet**.
- Pensado para TVs fracas: o modelo de referência tem 1,4 GB de RAM e tela 1280×720.
- Identidade visual própria: nenhum logotipo, texto ou asset da Apple ou de outra marca.
- Fonte [Inter](https://rsms.me/inter/) (licença SIL OFL 1.1, em `app/src/main/assets/licenses/Inter-OFL.txt`), reduzida aos caracteres do português: 3 pesos, 45 KB cada.

Princípios de design (das diretrizes de tvOS da Apple e das palestras de movimento da WWDC, aplicados com identidade própria): foco sem borda (cresce, ganha luz e um reflexo), movimento que desacelera sem passar do ponto, topo limpo, pouco texto, ordem da grade estável e respeito à opção do Android de remover animações.

## O que tem

| Recurso | Onde |
|---|---|
| Fundo escuro em degradê (4 temas: Noite, Grafite, Oceano, Aurora) ou preto puro | `ui/AmbientView.kt`, `ui/Ui.kt` |
| Dock de vidro com 4 apps favoritos, ícones grandes e arredondados | `ui/HomeScreen.kt`, `ui/Drawables.kt` (`GlassDrawable`) |
| Foco sem borda: o tile cresce, um reflexo atravessa o banner e ele afunda um pouco ao apertar OK | `ui/TileView.kt`, `ui/Drawables.kt` (`GlareDrawable`) |
| Luz na cor da arte atrás do tile em foco, uma por fileira, que desliza com o foco e nunca cobre os vizinhos | `ui/FocusGlow.kt`, `ui/Drawables.kt` (`HaloDrawable`) |
| Nome do app em destaque e brilho de fundo na cor da arte do app | `logic/ArtColor.kt`, `ui/AmbientView.kt` |
| Fundo cinematográfico: a arte do app em foco, desfocada, com zoom lento (só a GPU trabalha; para quando outro app está na tela) | `ui/AmbientView.kt` |
| "Recentes" (apps abertos por último, fora do dock) acima de "Todos os apps"; a ordem da grade não muda sozinha | `logic/Recents.kt`, `ui/HomeScreen.kt` |
| Grade com todos os apps ao apertar para baixo (4, 5 ou 6 colunas), com rolagem por página | `ui/HomeScreen.kt` |
| Atalhos só com ícone numa cápsula de vidro: Entradas, HDMI/AV, TV ao vivo, Rede, Ajustes, Personalizar (o nome aparece no título ao focar) | `ui/ShortcutButton.kt`, `TvShortcuts.kt` |
| Relógio, data e saudação discreta | `ui/HomeScreen.kt`, `logic/Greeting.kt` |
| Opções ao segurar OK (ou botão Menu): dock, ordem, ocultar, informações | `HomeActivity.kt` |
| Personalizar: tema, papel de parede, brilho, fundo com a arte, fundo em movimento, colunas, relógio, saudação, ocultos, ordem | `SettingsActivity.kt` |
| Protetor de tela "Relógio Clean TV", que muda de lugar a cada minuto | `ClockDreamService.kt` |
| Atualiza sozinho quando um app é instalado, removido, ativado ou desativado | `HomeActivity.kt` |
| Configuração pelo computador (dock, tema) via ADB | `ConfigReceiver.kt` |

### Desempenho

Na TV de referência (TCL Android TV 9, 1,4 GB, 1280×720), medido com `dumpsys gfxinfo`: ~8 ms por quadro parado e ~9 ms navegando (mediana), com 98% dos quadros dentro do prazo de 60 Hz. O segredo é o fundo em só duas camadas de tela cheia: a arte, o brilho e o escurecimento de cada app são pré-calculados numa imagem pequena, e o movimento lento do fundo é atualizado 20 vezes por segundo.

Navegação só com setas, OK, voltar e HOME. O botão voltar nunca fecha o launcher; ele só volta da grade para o dock.

## Compilar

Requisitos (instalados de forma portátil em `C:\dev\tools`): JDK 17, Android SDK (platform 34, build-tools 34.0.0) e Gradle 8.9 (ou o `gradlew` incluído).

```powershell
.\build.ps1              # APK de release + testes unitários
.\build.ps1 -Snapshots   # também regrava os prints das telas
```

O Gradle/Android não lida bem com caminhos com acento nem com pastas do OneDrive. Por isso o script espelha o código para `C:\dev\cleantv-launcher-build`, compila lá e traz de volta:

- o APK: `launcher\dist\clean-tv-launcher.apk`;
- os prints: `app\src\test\snapshots\images\` (gerados pelo Paparazzi no computador, sem emulador).

A chave de assinatura é criada uma vez em `C:\dev\cleantv-keys\` e fica fora do repositório. **Guarde uma cópia dela**: sem a mesma chave, não dá para atualizar o launcher instalado sem desinstalá-lo antes.

## Configurar pelo computador

O receptor só aceita comandos do shell do ADB (protegido por `WRITE_SECURE_SETTINGS`):

```
adb shell am broadcast -n com.cleantv.launcher/.ConfigReceiver \
  -a com.cleantv.launcher.action.CONFIGURE \
  --es dock com.netflix.ninja,com.google.android.youtube.tv,com.amazon.amazonvideo.livingroom \
  --es theme noite
```

## Instalar e testar sem trocar a tela inicial

O launcher também aparece como app comum na tela inicial original. Dá para instalar, abrir e testar antes de torná-lo o HOME. A troca de HOME é feita pela ferramenta `cleantv`, em ordem segura: instala, valida, define como HOME e só então, se você quiser, desativa o launcher original.
