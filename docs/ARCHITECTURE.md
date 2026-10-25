# Arquitetura — Clean TV

Ferramenta open source para limpar uma Android TV / Google TV pela rede local (ADB over Wi-Fi, sem root), de forma **reversível**, e trocar a tela inicial por um launcher próprio, minimalista.

## 1. O que a ferramenta faz e o que ela não faz

Faz:

- conecta na TV pela rede local (porta 5555), depois de confirmar IP e identidade da TV;
- tira um retrato completo da TV (backup) antes de qualquer mudança;
- classifica cada pacote instalado e monta um plano de mudanças;
- desativa pacotes aprovados com `pm disable-user` (reversível), em lotes pequenos;
- instala o launcher próprio, valida que ele funciona e só então (se você quiser) desativa o launcher original;
- gera relatório, script de restauração autônomo e o comando `cleantv restore`.

Não faz, por projeto:

- não desinstala pacotes do sistema, não apaga dados, não faz root, não desbloqueia bootloader, não altera firmware e não contorna DRM;
- não usa ADB pela internet (só endereços IPv4 privados são aceitos);
- não toca em pacote sem regra explícita (desconhecido = **não tocar**);
- não promete compatibilidade universal: Samsung Tizen e LG webOS estão fora do escopo.

## 2. Princípios

1. **Leitura antes de escrita.** Tudo começa em modo leitura. O modo padrão do `cleantv run` é dry-run; aplicar exige `--apply` **e** digitar `APLICAR`.
2. **Defesa em camadas.** Uma regra errada não basta para causar dano. Ver seção 6.
3. **Reversível sempre.** Só usamos operações que têm inversa direta (`disable-user` ↔ `enable`/`default-state`, `set-home-activity` ↔ `set-home-activity` original, instalar nosso launcher ↔ desinstalar nosso launcher).
4. **Auditável.** Python puro, sem dependências em tempo de execução. Regras em arquivos TOML legíveis. Todo comando enviado à TV vai para o log.
5. **Conservador por padrão.** Na dúvida, o pacote é classificado como "não tocar".

## 3. Stack

| Parte | Escolha | Por quê |
|---|---|---|
| Ferramenta no computador | Python 3.11+ (só biblioteca padrão) | Roda igual em Windows/macOS/Linux, fácil de ler e auditar, `tomllib` nativo para as regras, testes simples com pytest. Zero dependências reduz risco de supply chain. |
| Comunicação com a TV | Binário oficial `adb` (Google Platform Tools) via `subprocess` | É a implementação de referência do protocolo, com autenticação por chave. Reimplementar o protocolo seria mais código para auditar sem ganho real. |
| Regras | TOML versionado no repositório | Legível por humanos, comentável, fácil de revisar em pull request. |
| Launcher | Kotlin + Android SDK (API 26+), sem bibliotecas pesadas | Nativo, leve para TVs fracas, sem permissão de internet. Fase 5. |
| Testes | pytest + TV simulada (`FakeTv`) | Todo o fluxo (incluindo quedas de conexão) roda sem TV real. |

## 4. Estrutura de pastas

```
Projeto Tv/
├── README.md                  instalação, uso, riscos e recuperação
├── pyproject.toml             pacote Python "cleantv" (sem dependências)
├── docs/
│   ├── ARCHITECTURE.md        este documento
│   ├── IMPLEMENTATION_PLAN.md etapas e status
│   ├── COMPATIBILITY.md       matriz por marca/modelo
│   └── TROUBLESHOOTING.md     problemas comuns e recuperação
├── cleantv/                   ferramenta de terminal
│   ├── cli.py                 comandos e fluxo guiado (interface)
│   ├── ui.py                  perguntas, confirmações e tabelas no terminal
│   ├── network.py             checagem de rede local, IP privado, varredura da porta 5555
│   ├── adb/
│   │   ├── transport.py       execução do adb, validação de argumentos, mapeamento de erros
│   │   ├── guard.py           DryRunTransport: deixa passar leitura, bloqueia escrita
│   │   ├── fake.py            FakeTv: TV simulada com injeção de falhas
│   │   └── profiles/*.json    perfis sintéticos de TV para simulação
│   ├── device.py              operações de alto nível (getprop, pm, HOME, foreground)
│   ├── inventory.py           inventário de pacotes, launcher e configurações
│   ├── rules/
│   │   ├── safety.py          lista de proteção interna (não editável por regra)
│   │   ├── engine.py          carga das regras, precedência e classificação
│   │   └── data/              common.toml + brands/<marca>.toml
│   ├── planner.py             escolhas do usuário → plano de mudanças em lotes
│   ├── executor.py            aplicação em lotes, verificação, rollback, retomada
│   ├── journal.py             diário de execução gravado a cada passo
│   ├── backup.py              backup, plano de restauração e scripts autônomos
│   ├── report.py              relatório em Markdown
│   ├── check.py               pós-atualização: o que voltou desde a aplicação e plano para reaplicar
│   ├── paths.py, logsetup.py  pastas de dados e logs
│   └── constants.py           launchers conhecidos, componentes, categorias Android
├── tests/                     testes unitários e simulados (sem TV)
└── launcher/                  app Android (fase 5)
```

## 5. Componentes e fluxo

```
 você ──► cli.py ──► network.py (IP privado? mesma rede? porta 5555 aberta?)
                 │
                 ├─► adb/transport.py ──► adb connect + autorização na TV
                 │        └─ guard.py (leitura liberada, escrita bloqueada)
                 │
                 ├─► device.py / inventory.py ──► retrato da TV
                 ├─► backup.py ──► ~/.cleantv/devices/<id>/backups/original.json
                 ├─► rules/engine.py (+ safety.py) ──► classificação de cada pacote
                 ├─► planner.py ──► plano (lotes) ──► você revisa e confirma
                 ├─► executor.py ──► journal.py (grava cada passo)
                 │        └─ lote → verificação → saúde da TV → sua confirmação → próximo lote
                 ├─► report.py + scripts de restauração
                 └─► fim: desligar ADB na TV
```

Fluxo do `cleantv run` (segue o briefing):

1. Confirma que a TV é sua ou que você tem autorização.
2. Pergunta marca e modelo.
3. Valida a rede: o IP precisa ser privado (10/8, 172.16/12, 192.168/16) e estar na sua sub-rede. Se você não souber o IP, a ferramenta oferece uma varredura da porta 5555 **só na sua /24**.
4. Pede confirmação explícita do IP, conecta e espera você aceitar a chave na TV.
5. Lê a identidade da TV (fabricante, modelo, Android, build). Você confirma que é a TV certa.
6. Faz o inventário e grava o backup. O primeiro backup de cada TV vira o **ponto de restauração original** e nunca é sobrescrito.
7. Classifica os pacotes e mostra o resumo.
8. Pergunta: assistente de voz, Chromecast, atualizações, protetor de tela, itens recomendados/opcionais, apps a esconder, quatro apps do dock, troca de launcher.
9. Mostra o plano completo: pacote, motivo, risco e como desfazer.
10. Dry-run: mostra os comandos e termina. `--apply`: exige digitar `APLICAR` e executa em lotes.
11. Troca de launcher em ordem segura (seção 8).
12. Relatório, script de restauração e oferta para desligar a depuração ADB.

## 6. Modelo de segurança (camadas)

| Camada | O que impede |
|---|---|
| Validação de argumentos (`transport.py`) | Só tokens `[A-Za-z0-9_.:/=@%+,-]`. Não há como injetar `;`, `|`, `&&`, `$()` ou espaços no shell da TV. |
| `DryRunTransport` (`guard.py`) | Inventário, backup e dry-run usam um transporte que **fisicamente** bloqueia qualquer comando fora da lista de leitura (`getprop`, `pm list`, `dumpsys`, `resolve-activity`, `query-activities`, `settings get`). |
| Proteção interna (`safety.py`) | Lista no código de pacotes que nunca são desativados: Configurações, Play Store, Play Services, rede/Wi-Fi/Bluetooth, provedores, teclado, controle remoto, WebView, módulos mainline, chipsets (MediaTek, MStar, Realtek, Amlogic…), assistente de configuração. Arquivo de regra só a vence com `override_protection = true` **e** confirmação digitada do pacote. |
| Regras conservadoras (`engine.py`) | `disable` só vale com confiança `high`; média/baixa vira "opcional" (você precisa marcar). Pacote sem regra = não tocar. Heurísticas por nome só servem para **proteger** mais ou para sugerir como opcional. |
| Planejador (`planner.py`) | Nunca inclui launcher, quem responde ao HOME, assistente de configuração ou pacote já desativado. Tudo que foi barrado aparece no plano com o motivo. |
| Executor (`executor.py`) | Lotes pequenos (padrão 5). Antes de desativar, grava o estado original exato; depois, verifica o novo estado. Ao fim de cada lote: checa se a TV terminou o boot e se o HOME ainda resolve para um launcher. Pergunta se a TV está ok; se não estiver, desfaz o lote. |
| Diário (`journal.py`) | Cada passo é gravado em disco (escrita atômica) antes e depois de ir para a TV. Queda de conexão = parada segura + `cleantv resume`. |
| Rede | IP público/CGNAT/loopback recusados. Alerta se `ro.adb.secure=0`. No fim, oferece desligar a depuração ADB. |

## 7. Classificação e precedência de regras

Categorias (briefing): **manter**, **possível bloatware**, **anúncios/conteúdo patrocinado**, **telemetria/rastreamento**, **sistema crítico** e, por segurança, **não classificado (não tocar)**.

Ações: `disable` (proposto, já marcado), `ask` (opcional, desmarcado), `keep`, `protect` (nunca).

Ordem de decisão para cada pacote:

1. Proteção interna (`safety.py`).
2. Regra exata pelo nome (arquivo de modelo/marca vence o comum).
3. Regra por prefixo (o prefixo mais longo vence).
4. Heurística protetora (nome contém `ota`, `update`, `wifi`, `network`, `setup`, `input`, `hdmi`…).
5. Heurística suspeita (`ads`, `analytics`, `telemetry`, `acr`…), só fora de `android.*`, `com.android.*` e `com.google.android.*`. Sempre opcional e com confiança baixa.
6. App instalado por você (não-sistema): manter.
7. Sem regra: não tocar.

Regras podem ser filtradas por plataforma (`google_tv`, `android_tv`), SDK mínimo/máximo e regex de modelo, e podem pertencer a um grupo de escolha (`assistant`, `chromecast`, `updates`, `screensaver`) que só é aplicado conforme sua resposta.

Os arquivos de marca começam com `status = "nao-validado"`. Uma marca só passa para `validado` depois de testada num modelo real, e isso fica registrado em `docs/COMPATIBILITY.md`.

## 8. Troca de launcher (ordem segura)

1. Instalar o APK do nosso launcher (`adb install -r`). Se falhar (há TCLs que recusam), **para aqui**: nada mais muda.
2. Abrir o launcher e verificar que ele ficou em primeiro plano (não travou).
3. Definir como HOME (`cmd package set-home-activity`), apertar HOME e verificar que caiu no nosso launcher.
4. Só se você pediu: desativar o launcher original, apertar HOME e verificar de novo. Se o HOME cair no assistente de configuração (setupwraith), no seletor ou em app de fábrica, o launcher original é **reativado na hora**.

O assistente de configuração do Google TV (`com.google.android.tungsten.setupwraith`) nunca é desativado: segundo o projeto de referência, isso pode apagar a rede Wi-Fi salva e travar a tela inicial.

## 9. Backup, diário e restauração

- `backups/original.json`: primeiro retrato da TV (ponto de restauração). Cada nova execução grava também um retrato com data e hora.
- `runs/<run_id>.json`: diário com cada ação, o estado original exato (`enabled=0..4` do `dumpsys package`) e o resultado.
- `cleantv restore`: compara o backup original com o estado atual. Reativa tudo que estava ativo e agora está desativado, devolve o HOME original e, se você quiser, desinstala **apenas** o nosso launcher. Funciona mesmo sem o diário. Depois verifica se a TV voltou ao estado do backup.
- `restaurar.cmd` / `restaurar.sh`: scripts autônomos, regravados a cada lote, só com comandos `adb` simples. Servem para emergência, sem precisar do Python.

Estado original `0` (padrão do fabricante) é restaurado com `pm default-state`; se o Android não tiver esse comando, usa `pm enable`, que tem o mesmo efeito prático.

## 10. Falhas e retomada

| Situação | Comportamento |
|---|---|
| Wi-Fi caiu / TV desligou | O comando em andamento é marcado como "em execução"; nada mais é enviado; sai com código 3. `cleantv resume` reconecta, confirma que é a mesma TV, confere o estado real de cada ação pendente e continua. |
| Pacote recusado pelo Android ("protected package") | Ação marcada como falha, segue para o próximo; aparece no relatório. |
| Você responde "não" após um lote | O lote é desfeito e a execução para. |
| HOME quebrado após um lote | Alerta e oferta de desfazer o lote. |
| Ctrl+C | Diário salvo como interrompido; `resume` ou `restore` continuam de onde parou. |

## 11. Dados gravados no computador

```
~/.cleantv/                      (ou CLEANTV_HOME / --data-dir)
├── logs/run-AAAAMMDD-HHMMSS.log todos os comandos e saídas
├── sim/<perfil>.json            estado das TVs simuladas
└── devices/<id-da-tv>/
    ├── backups/original.json    ponto de restauração
    ├── backups/backup-*.json
    ├── runs/<run_id>.json       diários
    ├── reports/report-*.md
    ├── dock.json                apps escolhidos para o dock
    ├── restaurar.cmd
    └── restaurar.sh
```

## 12. Testes sem TV

`FakeTv` imita os comandos que a ferramenta usa (`getprop`, `pm`, `dumpsys`, `cmd package`, `settings`, `input`, `am`, `install`) com as saídas no formato real. Ela permite injetar falhas: queda de conexão depois de N comandos, pacote protegido, launcher que trava, TCL que recusa instalação e setupwraith que toma o HOME. Os mesmos testes cobrem dry-run (nenhuma escrita chega à TV), aplicação, retomada, rollback e ida e volta completa de restauração.

## 13. Limitações conhecidas

- Atualizações de firmware podem reativar pacotes e devolver o launcher original. Um comando `check` para detectar isso está no plano.
- As regras específicas de TCL, Xiaomi, Sony, Hisense e Skyworth ainda **não foram validadas** em TV real. Até lá, só valem as regras genéricas de Android TV/Google TV e as proteções dos namespaces dos fabricantes.
- A porta 5555 trafega sem criptografia; use só em rede doméstica confiável e desligue a depuração no final.
