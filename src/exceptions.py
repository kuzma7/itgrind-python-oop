class AccountFrozenError(Exception):
    pass


class AccountClosedError(Exception):
    pass


class InvalidOperationError(Exception):
    pass


class InsufficientFundsError(Exception):
    pass


class TemporaryTransactionError(Exception):
    pass


class BankOperationRestrictedError(InvalidOperationError):
    def __init__(self, retry_at):
        super().__init__("Bank operations are restricted from 00:00 to 05:00")
        self.retry_at = retry_at


class RiskBlockedError(InvalidOperationError):
    pass
