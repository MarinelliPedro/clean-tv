# Matriz de compatibilidade

A ferramenta não promete compatibilidade universal. Um pacote seguro de desativar num fabricante pode ser essencial em outro. Por isso cada marca tem seu arquivo de regras, com um status explícito.

## Status

| Status | Significado |
|---|---|
| `validado` | Testado em pelo menos um modelo real, com inventário, aplicação e restauração conferidos. |
| `parcial` | Regras usadas na prática, mas sem cobertura de todos os modelos. |
| `nao-validado` | Ainda sem teste em TV real. Só valem as regras genéricas e as proteções; pacotes do fabricante ficam como "não tocar". |

## Plataformas

| Plataforma | Suporte |
|---|---|
| Google TV (Android 10+) | MVP |
| Android TV 8–14 (interface antiga) | MVP |
| Fire TV (Fire OS) | Fora do escopo: o Fire OS não permite trocar o HOME por um launcher de terceiros. |
| Samsung Tizen, LG webOS, Hisense VIDAA, Roku | Fora do escopo: não usam Android/ADB. |

## Marcas

| Marca | Arquivo | Status | O que vale hoje | Notas |
|---|---|---|---|---|
| Genérico Android TV / Google TV | `common.toml` | parcial | YouTube Music, Play Games e cliente ACR Inscape (propostos); recomendações, feedback e loja de filmes (opcionais); grupos de assistente, Chromecast e protetor de tela | Base para todas as marcas |
| TCL | `brands/tcl.toml` | parcial | Regras genéricas + proteção de TV, entradas, fontes, atualização, configuração inicial, controle e teclado da TCL; opcionais no modelo UnionTV: `com.tcl.bi` (telemetria), `com.tcl.esticker`, `com.tcl.tvweishi`, `com.tcl.appmarket2` | Algumas TCL recusam instalar launcher de terceiros. `com.tcl.partnercustomizer.resource` tem um serviço que pode reimpor o launcher original |
| Xiaomi / Mi TV | `brands/xiaomi.toml` | nao-validado | Regras genéricas + proteção do PatchWall (`com.mitv.tvhome`) e do app de fábrica (`com.duokan.factorytest`) | O app de fábrica responde ao HOME |
| Sony Bravia | `brands/sony.toml` | nao-validado | Só regras genéricas | — |
| Hisense (Android/Google TV) | `brands/hisense.toml` | nao-validado | Só regras genéricas | Modelos VIDAA não são suportados |
| Skyworth | `brands/skyworth.toml` | nao-validado | Só regras genéricas | — |

Os chipsets comuns em TVs (MediaTek, MStar, Realtek, Amlogic, Novatek, HiSilicon) são protegidos para todas as marcas em `cleantv/rules/safety.py`.

## Modelos testados

| Marca | Modelo | Android | Plataforma | Data | Resultado |
|---|---|---|---|---|---|
| TCL | UnionTV (software V8-R41KT01-LF1V325, chipset Realtek) | 9 | Android TV (`com.google.android.tvlauncher`) | 25/10/2026 | Inventário OK (113 pacotes). **16 pacotes desativados em 4 lotes**, incluindo `com.tcl.bi`, `com.tcl.tvweishi`, `com.tcl.appmarket2` e `com.tcl.esticker`; TV reiniciada e funcionando. Restauração conferida só em dry-run. **Launcher Clean TV instalado e definido como HOME**: esta TCL aceita launcher de terceiros, mas o `tvlauncher` declara prioridade de sistema 2 no HOME, então ele precisa ser desativado (`--set-home --disable-stock`). Depois de um reinício real, o HOME continuou no Clean TV: o serviço da TCL não reimpôs o launcher original. Perfil simulado: `tcl-uniontv-atv9`. |

## Como adicionar regras para um modelo

1. Rode o inventário somente leitura e salve a classificação:
   ```powershell
   python -m cleantv inventory --ip <IP> --brand TCL --model <modelo> --json tcl-<modelo>.json
   ```
2. Pesquise cada pacote candidato e anote o que ele faz no seu modelo.
3. Crie as regras num arquivo `.toml` (em `cleantv/rules/data/brands/` ou numa pasta passada com `--rules-dir`):
   ```toml
   [[rule]]
   package = "com.exemplo.canal.patrocinado"
   category = "ads"             # ads | telemetry | bloatware | keep | critical | unknown
   action = "ask"               # comece sempre como opcional
   confidence = "medium"
   reason = "O que o pacote faz, em uma frase."
   risk = "O que deixa de funcionar."
   models = ["^55C7"]           # opcional: regex do modelo
   ```
   `action = "disable"` exige `confidence = "high"`, e uma regra só fica `high` depois de testada.
4. Teste com `run` (dry-run), depois `run --apply` com `--batch-size 1`, e por fim `restore`.
5. Registre o modelo na tabela acima e, se tudo deu certo, mude o status do arquivo.
