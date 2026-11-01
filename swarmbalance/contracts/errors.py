"""Application failures translated by the transport adapter."""
class ApplicationError(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
