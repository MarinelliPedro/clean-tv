# Como contribuir

Obrigado por querer ajudar! O Clean TV fica melhor a cada modelo de TV testado.

## A contribuição mais valiosa: a sua TV

Um pacote seguro de desativar numa marca pode ser essencial em outra. Por isso as regras são por marca e só viram "validadas" depois de testadas numa TV real.

1. **Inventário somente leitura** (não altera nada na TV):
   ```powershell
   python -m cleantv inventory --ip <IP-da-TV> --brand <Marca> --model <Modelo> --json minha-tv.json
   ```
2. **Abra uma issue "Nova TV"** com o modelo, a versão do Android e o `minha-tv.json`. Antes de anexar, confira o arquivo: ele traz a lista de pacotes e a identificação da TV. Se quiser, troque o número de série (`serial`) por qualquer texto.
3. **Quer escrever as regras?** Siga [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md#como-adicionar-regras-para-um-modelo). Toda regra nova começa como `action = "ask"`; `disable` só com `confidence = "high"`, depois de testada com `run --apply --batch-size 1` e `restore`.

Regras de ouro:

- Na dúvida, o pacote fica como "não tocar".
- Nunca proponha desativar Configurações, Play Store, rede, teclado, controle, chipset, atualizações ou o assistente de configuração. Essas proteções ficam em `cleantv/rules/safety.py` e não podem ser derrubadas por arquivo de regra.
- Cada regra diz **o que o pacote faz** (`reason`) e **o que deixa de funcionar** (`risk`).

## Código

```powershell
git clone https://github.com/<você>/clean-tv.git
cd clean-tv
python -m pip install -e ".[dev]"
python -m pytest
```

- Python 3.11+, sem dependências de execução. Mantenha assim.
- Todo comando enviado à TV passa por `cleantv/adb/transport.py` (validação de argumentos) e, no dry-run, por `DryRunTransport` (bloqueia escrita).
- Teste contra a TV simulada (`cleantv/adb/fake.py`). Se o seu caso depende de um comportamento real do Android, reproduza esse comportamento no simulador e escreva o teste.
- Textos para o usuário em português do Brasil, diretos e sem jargão.

### Launcher (Android)

```powershell
.\launcher\build.ps1              # APK + testes
.\launcher\build.ps1 -Snapshots   # também regrava os prints
```

Kotlin com Views nativas, sem bibliotecas e sem permissão de internet. Pense em TVs fracas: meça com `adb shell dumpsys gfxinfo com.cleantv.launcher` antes e depois de mudanças visuais. Detalhes em [launcher/README.md](launcher/README.md).

## Pull requests

- Um assunto por PR, com testes.
- Descreva como testou (simulador, TV real e modelo).
- Mudanças em regras: diga em qual TV foram testadas e o resultado do `restore`.
