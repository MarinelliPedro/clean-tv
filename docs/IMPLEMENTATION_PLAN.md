# Plano de implementação

Cada etapa termina com testes passando e só então a próxima começa. As etapas que mexem na TV real exigem sua confirmação explícita.

| # | Etapa | Entregas | Toca na TV real? | Status |
|---|---|---|---|---|
| 0 | Ambiente | Python 3.12, ADB (Platform Tools), pytest | não | feito |
| 1 | Arquitetura e plano | `docs/ARCHITECTURE.md`, este arquivo | não | feito |
| 2 | Núcleo em dry-run | transporte + guarda, TV simulada, inventário, regras, planejador, CLI guiada, relatório | não | feito |
| 3 | Backup e restauração | ponto de restauração original, diário, `cleantv restore`, scripts autônomos, testes de ida e volta | não (simulado) | feito |
| 4 | Aplicação reversível | executor em lotes, verificação, rollback por lote, retomada após queda, testes de falha | não (simulado) | feito |
| 4a | **Primeiro contato com a sua TCL** | `cleantv inventory` (somente leitura): TCL UnionTV, Android TV 9, 113 pacotes, ponto de restauração original gravado | **sim, só leitura** | feito (25/10/2026) |
| 4b | Regras TCL | `dumpsys` dos pacotes da TCL, regras com evidência em `brands/tcl.toml`, perfil simulado `tcl-uniontv-atv9` | não | feito (falta validar com 4d) |
| 4c | Dry-run na TV real | `cleantv run` sem `--apply`: 16 pacotes em 4 lotes, nada aplicado | **sim, só leitura** | feito (25/10/2026) |
| 4d | Aplicação real | `run --apply --max-batches 1` + `resume`, um lote por vez, com conferência na TV e reinício entre lotes | **sim, com sua confirmação** | feito (25/10/2026): 16/16 |
| 5 | Launcher Android | ferramentas portáteis em `C:\dev\tools`; Kotlin sem bibliotecas, APK de 58 KB; dock de vidro, grade, brilho pela arte, atalhos, relógio, temas, protetor de tela; prints pelo Paparazzi (o PC não roda emulador: virtualização desligada na BIOS) | não | feito no computador (25/10/2026) |
| 6 | Integração do launcher | comando `cleantv launcher`: instala, valida, envia o dock; modo de teste ou `--set-home`; trata launcher original com prioridade de sistema | **sim, com sua confirmação** | feito (25/10/2026): Clean TV é o HOME da TCL |
| 7 | Pós-atualização | `cleantv check`: compara diários, backup e TV; mostra pacotes reativados, launcher original de volta, HOME trocado e pacotes novos; `--apply` reaplica pelo executor | sim, leitura (`--apply` com confirmação) | feito (25/10/2026): TV real conferida, 16/16 em ordem |
| 8 | Documentação e publicação | README, compatibilidade, troubleshooting, CONTRIBUTING, SECURITY, CI no GitHub, release do APK | não | publicação: 25/10/2026 |

## Detalhe das próximas etapas

### 4a. Inventário somente leitura da TCL

Na TV:

1. Configurações → Sistema → Sobre → clicar 7 vezes em "Build do sistema operacional Android TV" para liberar as opções do desenvolvedor.
2. Configurações → Sistema → Opções do desenvolvedor → ativar "Depuração USB" (em algumas TCL também existe "Depuração de rede" ou "ADB pela rede").
3. Anotar o IP da TV: Configurações → Rede e Internet → sua rede.

No computador:

```powershell
python -m cleantv inventory --ip <IP-da-TV> --brand TCL --model <modelo>
```

Esse comando só lê dados (o `DryRunTransport` bloqueia qualquer escrita). Ele mostra a identidade da TV, pede sua confirmação, grava o backup original e lista a classificação de todos os pacotes.

### 5. Launcher

Antes de começar: instalar JDK 17 e o Android SDK (command-line tools, platform 34, build-tools) via winget/sdkmanager. O build deve rodar numa pasta sem acentos e fora do OneDrive (por exemplo `C:\dev\cleantv-launcher`), porque o Gradle/AGP tem problemas com caminhos não ASCII e com a sincronização do OneDrive.
