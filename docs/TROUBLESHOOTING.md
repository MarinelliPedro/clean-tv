# Problemas comuns

Em qualquer dúvida, o log completo de cada execução fica em `~/.cleantv/logs/` (com todos os comandos enviados e as respostas da TV).

## "ADB não encontrado"

Instale o Platform Tools (`winget install Google.PlatformTools` no Windows) e abra um terminal novo. Se ainda assim não achar, informe o caminho: `python -m cleantv --adb "C:\caminho\adb.exe" doctor`.

## "A porta 5555 da TV não respondeu"

- Confira se a TV e o computador estão no mesmo roteador/Wi-Fi (o `doctor` mostra o IP do computador; os três primeiros números costumam ser iguais aos da TV).
- Na TV, confira se **Depuração USB** está ativa e, se existir, **Depuração de rede / ADB pela rede**.
- Algumas TVs desligam a depuração ao reiniciar: ative de novo.
- Redes de convidados e alguns roteadores isolam os aparelhos entre si ("isolamento de clientes"). Use a rede principal.

## A TV não mostra o aviso "Permitir depuração?" (ou fica "unauthorized")

- Olhe a TV logo depois de rodar o comando; o aviso pode sumir sozinho.
- Desligue e ligue a **Depuração USB** na TV e rode de novo.
- No computador: `adb kill-server` e tente outra vez.
- Nas Opções do desenvolvedor, "Revogar autorizações de depuração" e tente de novo.

## A conexão caiu no meio da execução

Nada mais foi enviado à TV depois da queda. Quando ela voltar:

```powershell
python -m cleantv resume --ip <IP>     # continua de onde parou
python -m cleantv restore --ip <IP>    # ou desfaz tudo
```

O `resume` confere o estado real de cada pacote antes de continuar, então não repete nem pula nada.

## Depois da troca de launcher, o HOME mostra um seletor, uma tela preta ou o assistente de configuração

1. `python -m cleantv restore --ip <IP>`.
2. Se o computador não estiver à mão, rode o `restaurar.cmd` / `restaurar.sh` gerado na pasta da TV em `~/.cleantv/devices/`.
3. Manualmente:
   ```
   adb -s <IP>:5555 shell pm enable com.google.android.apps.tv.launcherx
   adb -s <IP>:5555 shell cmd package set-home-activity --user 0 com.google.android.apps.tv.launcherx/com.google.android.apps.tv.launcherx.home.HomeActivity
   ```
   (Android TV antigo: `com.google.android.tvlauncher`.)

A ferramenta nunca desativa o assistente de configuração do Google TV (`setupwraith`), porque isso pode apagar a rede Wi-Fi salva e travar a tela inicial.

## Desativei um app, mas o ícone continua na tela inicial

A tela inicial do Android TV guarda os atalhos da fileira "Apps favoritos" e só recarrega a lista quando o processo dela reinicia. Desligar pelo controle normalmente só coloca a TV em **modo de espera** (confira com `adb shell cat /proc/uptime`). Para atualizar:

- reinicie de verdade: Configurações → Preferências do dispositivo → Sobre → **Reiniciar**, ou tire a TV da tomada por 10 segundos; ou
- segure OK sobre o atalho e escolha **Remover dos favoritos**.

O app em si já está desativado; o atalho só abre a Play Store ou não faz nada.

## A TV recusou instalar o launcher

Algumas TCL bloqueiam launchers de terceiros. A ferramenta para na instalação e não mexe no launcher original. A limpeza de pacotes continua valendo.

## O botão de voz / a transmissão do celular / o protetor de tela pararam

São efeitos esperados de desativar o Assistente (`com.google.android.katniss`), o Chromecast (`com.google.android.apps.mediashell`) ou o modo ambiente. Para voltar só um deles:

```
adb -s <IP>:5555 shell pm enable <pacote>
```

ou rode `restore` para voltar tudo.

## Depois de uma atualização da TV, os anúncios voltaram

Atualizações de firmware podem reativar pacotes e devolver o launcher original. Rode `python -m cleantv check --ip <IP>`: ele mostra o que voltou sem alterar nada, e `check --apply` reaplica só isso. Para revisar pacotes novos que a atualização trouxe, rode `run` de novo. O ponto de restauração original é mantido, então `restore` continua levando ao estado de fábrica.

## O launcher não anima (fundo parado, sem reflexo, foco "pulando")

O Clean TV respeita a opção do Android de remover animações. Muitas TVs (a TCL testada, por exemplo) já vêm de fábrica com as escalas de animação em 0. Para ligar só as animações dentro dos apps, mantendo instantânea a troca entre apps:

```
adb -s <IP>:5555 shell settings put global animator_duration_scale 1
```

Para desligar de novo: o mesmo comando com `0`. Se preferir, desligue só o movimento do fundo em **Personalizar → Fundo em movimento**.

## Perdi a pasta `~/.cleantv` (backup e diários)

- Os pacotes que a ferramenta desativou aparecem em `adb -s <IP>:5555 shell pm list packages -d`. Reative com `pm enable <pacote>`.
- O relatório (se você guardou) lista cada pacote e o comando para desfazer.
- Último recurso: a restauração de fábrica da TV reativa tudo, mas apaga apps e logins.

## O build do launcher falha com caminho com acento / OneDrive (etapa 5)

O Gradle/Android Gradle Plugin tem problemas com caminhos não ASCII (como "Área de Trabalho") e com pastas sincronizadas pelo OneDrive. Compile o launcher numa pasta como `C:\dev\cleantv-launcher`.
