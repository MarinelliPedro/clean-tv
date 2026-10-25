"""Exceções da ferramenta. As mensagens já são escritas para o usuário final."""


class CleanTvError(Exception):
    """Erro esperado, com mensagem pronta para mostrar ao usuário."""


class AdbNotFound(CleanTvError):
    pass


class AdbError(CleanTvError):
    pass


class ConnectionLost(AdbError):
    """A TV parou de responder (Wi-Fi caiu, TV desligou ou depuração revogada)."""


class DeviceUnauthorized(AdbError):
    """A TV ainda não aceitou a chave ADB deste computador."""


class UnsafeCommand(CleanTvError):
    """Comando recusado pela validação de argumentos."""


class UserAborted(CleanTvError):
    """O usuário escolheu parar."""
