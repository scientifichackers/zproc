class ProcessWaitError(Exception):
    """
    Raised when there is a pr
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        try:
            self.exitcode = kwargs.pop("exitcode")
        except KeyError:
            pass
        super().__init__(*args, **kwargs)
