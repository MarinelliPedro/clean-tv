# Segurança e uso responsável

## Uso responsável

- Use o Clean TV **apenas em TVs suas** ou com autorização explícita do dono.
- **Nunca exponha o ADB à internet.** A ferramenta só aceita IPs de rede privada e oferece desligar a depuração no fim. Faça isso quando terminar (`cleantv finish`).
- O projeto não faz root, não desbloqueia bootloader, não altera firmware e não contorna DRM. Pedidos nesse sentido não serão aceitos.

## O que a ferramenta guarda no seu computador

Em `~/.cleantv/` (ou na pasta de `--data-dir`): backups com a lista de pacotes e a identificação da TV, diários de execução, relatórios e logs. Nada é enviado para fora. O launcher não tem permissão de internet.

Não publique essa pasta nem os logs sem revisar: eles contêm o IP da TV na sua rede e o número de série dela.

## Como relatar uma vulnerabilidade

Use o [relato privado de vulnerabilidades do GitHub](https://docs.github.com/pt/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) (aba **Security** do repositório → **Report a vulnerability**). Não abra issue pública para falhas de segurança.

Exemplos do que importa: um caminho em que a ferramenta envie um comando de escrita durante o dry-run, aceite um IP público, desative um pacote protegido ou deixe a TV sem tela inicial.
